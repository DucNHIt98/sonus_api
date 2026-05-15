import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Thread

from django.core.cache import cache
from django.db.models import F
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from services.nct import get_chart as nct_get_chart, resolve_audio as nct_resolve_audio, search as nct_search
from services.jamendo import JamendoError
from services.jamendo import search as jamendo_search
from services.jamendo import get_tracks_by_genre as jamendo_genre
from services.jamendo import get_discovery as jamendo_discovery
from services.youtube import YouTubeError, extract_audio_url, search_youtube, get_autocomplete
from services.youtube import convert_deezer_to_youtube, get_related_videos

from core.permissions import FREE_DOWNLOAD_LIMIT, FREE_SEARCH_LIMIT, FREE_HISTORY_DAYS, FREE_FAVORITE_LIMIT, is_premium

from .models import DownloadedSong, LikedSong, Lyric, PlayHistory, Song
from .serializers import (
    DownloadSongSerializer,
    DownloadedSongSerializer,
    LikedSongSerializer,
    LyricSerializer,
    PlayHistorySerializer,
    RecordPlaySerializer,
    ResolveAudioSerializer,
    SearchSerializer,
)


def _normalize(s):
    return re.sub(r'[^a-z0-9]', '', s.lower().strip()) if s else ''


_YOUTUBE_ID_RE = re.compile(r'^[A-Za-z0-9_-]{11}$')


def _background_save_results(results: list):
    from services.crawler import _save_songs
    _save_songs(results, 'search_cache')


class ResolveAudioView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ResolveAudioSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        video_id = data.get('video_id') or data.get('youtube_id')

        if video_id:
            try:
                result = extract_audio_url(video_id)
                return Response({
                    'youtube_id': video_id,
                    'audio_url': result['audio_url'],
                    'expires_at': result['expires_at'],
                    'title': result.get('title'),
                    'duration': result.get('duration'),
                })
            except YouTubeError as e:
                return Response({'detail': str(e)}, status=status.HTTP_502_BAD_GATEWAY)

        nct_url = data.get('nct_url')
        if nct_url:
            result = nct_resolve_audio(nct_url)
            if not result:
                return Response(
                    {'detail': 'Could not resolve NCT audio'},
                    status=status.HTTP_404_NOT_FOUND,
                )
            return Response({
                'audio_url': result['audio_url'],
                'source': 'nct',
            })

        title = data.get('title')
        artist = data.get('artist', '')

        if title:
            try:
                yt_data = convert_deezer_to_youtube(title, artist)
                if not yt_data:
                    return Response(
                        {'detail': 'Could not find YouTube match'},
                        status=status.HTTP_404_NOT_FOUND,
                    )
                audio = extract_audio_url(yt_data['id'])
                return Response({
                    'youtube_id': yt_data['id'],
                    'audio_url': audio['audio_url'],
                    'expires_at': audio['expires_at'],
                    'title': audio.get('title', title),
                    'duration': audio.get('duration'),
                })
            except YouTubeError as e:
                return Response({'detail': str(e)}, status=status.HTTP_502_BAD_GATEWAY)

        return Response(
            {'detail': 'Provide video_id, youtube_id, or title'},
            status=status.HTTP_400_BAD_REQUEST,
        )


class SearchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = SearchSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        params = serializer.validated_data

        query = params['q']
        limit = params['limit']
        sources = params['sources'].split(',')

        futures = {}
        errors = []

        with ThreadPoolExecutor(max_workers=3) as ex:
            if 'youtube' in sources:
                futures['youtube'] = ex.submit(search_youtube, query, limit)
            if 'jamendo' in sources:
                futures['jamendo'] = ex.submit(jamendo_search, query, limit)
            if 'nct' in sources:
                futures['nct'] = ex.submit(nct_search, query, limit)

        results = []
        for name, future in futures.items():
            try:
                results.extend(future.result())
            except YouTubeError as e:
                errors.append(f'youtube: {e}')
            except JamendoError as e:
                errors.append(f'jamendo: {e}')
            except Exception:
                errors.append(f'{name}: failed')

        Thread(target=_background_save_results, args=(results,), daemon=True).start()

        seen = set()
        deduped = []
        for r in results:
            key = (_normalize(r.get('title', '')), _normalize(r.get('subtitle', '')))
            if key not in seen and r.get('title'):
                seen.add(key)
                deduped.append(r)

        truncated = False
        if not is_premium(str(request.user.id)):
            truncated = len(deduped) > FREE_SEARCH_LIMIT
            deduped = deduped[:FREE_SEARCH_LIMIT]

        return Response({
            'results': deduped[:limit],
            'total': len(deduped),
            'truncated': truncated,
            'errors': errors if errors else None,
        })


class AutocompleteView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        q = request.query_params.get('q', '')
        if not q or len(q) < 2:
            return Response({'suggestions': []})

        suggestions = get_autocomplete(q)
        return Response({'suggestions': suggestions})


class HomeFeedView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cache_key = 'home_feed:global'
        cached = cache.get(cache_key)
        if cached:
            if not is_premium(str(request.user.id)):
                cached = {'genres': cached.get('genres', {})}
            return Response(cached)

        charts = {}
        chart_regions = ['v-pop', 'us-uk', 'k-pop', 'v-rap', 'billboard']
        for region in chart_regions:
            try:
                charts[region] = nct_get_chart(region)
            except Exception:
                charts[region] = []

        genres = {}
        genre_slugs = ['rock', 'pop', 'hip-hop', 'electronic', 'jazz', 'folk']
        for genre in genre_slugs:
            try:
                genres[genre] = jamendo_genre(genre, 10)
            except JamendoError:
                genres[genre] = []

        trending = []
        try:
            trending = jamendo_discovery(20)
        except JamendoError:
            trending = []

        feed = {
            'trending': trending,
            'charts': charts,
            'genres': genres,
        }

        if not is_premium(str(request.user.id)):
            feed = {
                'genres': genres,
            }

        cache.set(cache_key, feed, timeout=1800)
        return Response(feed)


class ChartDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not is_premium(str(request.user.id)):
            return Response(
                {'detail': 'Charts are a Premium feature. Upgrade to access full chart details.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        region = request.query_params.get('region', '')
        if not region:
            return Response({'detail': 'region parameter is required'}, status=status.HTTP_400_BAD_REQUEST)

        tracks = nct_get_chart(region)
        return Response({'region': region, 'tracks': tracks})


class GenreTrackListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not is_premium(str(request.user.id)):
            return Response(
                {'detail': 'Genre tracks are a Premium feature. Upgrade to access full genre details.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        genre = request.query_params.get('genre', '')
        if not genre:
            return Response({'detail': 'genre parameter is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            tracks = jamendo_genre(genre, 20)
            return Response({'genre': genre, 'tracks': tracks})
        except JamendoError as e:
            return Response({'detail': str(e)}, status=status.HTTP_502_BAD_GATEWAY)


class RecordPlayView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = RecordPlaySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        song_id = data['song_id']

        Song.objects.get_or_create(
            id=song_id,
            defaults={
                'title': data.get('title', ''),
                'subtitle': data.get('subtitle', ''),
                'image_url': data.get('image_url', ''),
                'duration': data.get('duration'),
                'source': 'youtube',
            },
        )

        history, created = PlayHistory.objects.get_or_create(
            user=request.user,
            song_id=song_id,
            defaults={'count': 1, 'last_played': timezone.now()},
        )
        if not created:
            PlayHistory.objects.filter(pk=history.pk).update(
                count=F('count') + 1,
                last_played=timezone.now(),
            )
            history.refresh_from_db()

        return Response({'detail': 'Play recorded', 'count': history.count})


class PlayHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        offset = int(request.query_params.get('offset', 0))
        limit = int(request.query_params.get('limit', 20))

        qs = PlayHistory.objects.filter(user=request.user)\
            .select_related('song')\
            .order_by('-last_played')

        if not is_premium(str(request.user.id)):
            cutoff = timezone.now() - timedelta(days=FREE_HISTORY_DAYS)
            qs = qs.filter(last_played__gte=cutoff)

        total = qs.count()

        history = []
        for h in qs[offset:offset + limit]:
            s = h.song
            history.append({
                'count': h.count,
                'last_played': h.last_played,
                'song': {
                    'id': s.id,
                    'title': s.title,
                    'subtitle': s.subtitle,
                    'image_url': s.image_url,
                    'audio_url': s.audio_url,
                    'duration': s.duration,
                    'source': s.source,
                },
            })

        return Response({'history': history, 'total': total})

    def delete(self, request):
        song_id = request.query_params.get('song_id')
        qs = PlayHistory.objects.filter(user=request.user)

        if song_id:
            deleted, _ = qs.filter(song_id=song_id).delete()
            if deleted == 0:
                return Response({'detail': 'History entry not found'}, status=status.HTTP_404_NOT_FOUND)
            return Response({'detail': 'History entry deleted'})
        else:
            qs.delete()
            return Response({'detail': 'All history cleared'})


class TopPlayedView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        limit = int(request.query_params.get('limit', 10))

        qs = PlayHistory.objects.filter(user=request.user)\
            .select_related('song')\
            .order_by('-count')

        if not is_premium(str(request.user.id)):
            cutoff = timezone.now() - timedelta(days=FREE_HISTORY_DAYS)
            qs = qs.filter(last_played__gte=cutoff)

        qs = qs[:limit]

        top = []
        for h in qs:
            s = h.song
            top.append({
                'count': h.count,
                'last_played': h.last_played,
                'song': {
                    'id': s.id,
                    'title': s.title,
                    'subtitle': s.subtitle,
                    'image_url': s.image_url,
                    'audio_url': s.audio_url,
                    'duration': s.duration,
                    'source': s.source,
                },
            })

        return Response({'top': top})


class FavoriteToggleView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, song_id):
        liked = request.data.get('liked', True)

        if liked:
            if not is_premium(str(request.user.id)):
                current_count = LikedSong.objects.filter(user=request.user).count()
                if current_count >= FREE_FAVORITE_LIMIT:
                    return Response(
                        {'detail': f'Favorite limit reached ({FREE_FAVORITE_LIMIT}). Upgrade to Premium for unlimited favorites.'},
                        status=status.HTTP_403_FORBIDDEN,
                    )

            LikedSong.objects.get_or_create(
                user=request.user,
                song_id=song_id,
                defaults={'liked_at': timezone.now()},
            )
            return Response({'detail': 'Added to favorites', 'liked': True})
        else:
            LikedSong.objects.filter(user=request.user, song_id=song_id).delete()
            return Response({'detail': 'Removed from favorites', 'liked': False})


class FavoriteListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        offset = int(request.query_params.get('offset', 0))
        limit = int(request.query_params.get('limit', 20))

        qs = LikedSong.objects.filter(user=request.user)\
            .select_related('song')\
            .order_by('-liked_at')
        total = qs.count()

        favorites = []
        for ls in qs[offset:offset + limit]:
            s = ls.song
            favorites.append({
                'created_at': ls.liked_at,
                'song': {
                    'id': s.id,
                    'title': s.title,
                    'subtitle': s.subtitle,
                    'image_url': s.image_url,
                    'audio_url': s.audio_url,
                    'duration': s.duration,
                    'source': s.source,
                },
            })

        return Response({'favorites': favorites, 'total': total})


class DownloadSongView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, song_id):
        serializer = DownloadSongSerializer(data={'song_id': song_id, **request.data})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        Song.objects.get_or_create(
            id=song_id,
            defaults={
                'title': data.get('title', ''),
                'subtitle': data.get('subtitle', ''),
                'image_url': data.get('image_url', ''),
                'audio_url': data.get('audio_url', ''),
                'duration': data.get('duration'),
                'source': data.get('source', ''),
            },
        )

        already = DownloadedSong.objects.filter(user=request.user, song_id=song_id).first()
        if already:
            return Response({'detail': 'Song already downloaded', 'downloaded_at': already.downloaded_at})

        if not is_premium(str(request.user.id)):
            current_count = DownloadedSong.objects.filter(user=request.user).count()
            if current_count >= FREE_DOWNLOAD_LIMIT:
                return Response(
                    {'detail': f'Download limit reached ({FREE_DOWNLOAD_LIMIT}). Upgrade to Premium for unlimited downloads.'},
                    status=status.HTTP_403_FORBIDDEN,
                )

        downloaded = DownloadedSong.objects.create(user=request.user, song_id=song_id)
        return Response(
            {'detail': 'Song downloaded', 'downloaded_at': downloaded.downloaded_at},
            status=status.HTTP_201_CREATED,
        )

    def delete(self, request, song_id):
        deleted, _ = DownloadedSong.objects.filter(user=request.user, song_id=song_id).delete()
        if deleted == 0:
            return Response({'detail': 'Downloaded song not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'detail': 'Download removed'}, status=status.HTTP_200_OK)


class DownloadedSongsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        offset = int(request.query_params.get('offset', 0))
        limit = int(request.query_params.get('limit', 20))

        qs = DownloadedSong.objects.filter(user=request.user)\
            .select_related('song')\
            .order_by('-downloaded_at')
        total = qs.count()

        downloads = []
        for d in qs[offset:offset + limit]:
            s = d.song
            downloads.append({
                'downloaded_at': d.downloaded_at,
                'song': {
                    'id': s.id,
                    'title': s.title,
                    'subtitle': s.subtitle,
                    'image_url': s.image_url,
                    'audio_url': s.audio_url,
                    'duration': s.duration,
                    'source': s.source,
                },
            })

        return Response({'downloads': downloads, 'total': total})


class RelatedView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, song_id):
        limit = int(request.query_params.get('limit', 10))

        if _YOUTUBE_ID_RE.match(song_id):
            results = get_related_videos(song_id, limit)
        else:
            song = Song.objects.filter(id=song_id).first()
            if not song or not song.title:
                return Response({'results': [], 'total': 0})
            try:
                results = search_youtube(f'{song.title} {song.subtitle or ""}', limit)
            except YouTubeError:
                results = []

        return Response({
            'results': results[:limit],
            'total': len(results),
        })


class LyricsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, song_id):
        try:
            lyric = Lyric.objects.get(pk=song_id)
        except Lyric.DoesNotExist:
            from services.lyrics import fetch_and_store_lyrics
            lyric = fetch_and_store_lyrics(song_id)
            if not lyric:
                return Response(
                    {'detail': 'Lyrics not available for this song'},
                    status=status.HTTP_404_NOT_FOUND,
                )
        serializer = LyricSerializer(lyric)
        return Response(serializer.data)


class DownloadQuotaView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        premium = is_premium(str(request.user.id))
        current_count = DownloadedSong.objects.filter(user=request.user).count()

        return Response({
            'is_premium': premium,
            'downloads_used': current_count,
            'downloads_limit': None if premium else FREE_DOWNLOAD_LIMIT,
        })
