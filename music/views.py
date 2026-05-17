import hashlib
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Thread

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.db.models import F, Q
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


def _cache_key(prefix: str, *parts) -> str:
    raw = '|'.join(str(part) for part in parts)
    digest = hashlib.sha256(raw.encode('utf-8')).hexdigest()
    return f'{prefix}:{digest}'


def _is_premium_cached(user_id: str) -> bool:
    key = f'user-premium:{user_id}'
    cached = cache.get(key)
    if cached is not None:
        return cached
    premium = is_premium(user_id)
    cache.set(key, premium, timeout=60)
    return premium


def _normalize(s):
    return re.sub(r'[^a-z0-9]', '', s.lower().strip()) if s else ''


_YOUTUBE_ID_RE = re.compile(r'^[A-Za-z0-9_-]{11}$')


def _background_save_results(results: list):
    from services.crawler import _save_songs
    _save_songs(results, 'search')


def _song_to_search_result(song: Song) -> dict:
    return {
        'id': song.id,
        'title': song.title or '',
        'subtitle': song.subtitle or '',
        'image_url': song.image_url or '',
        'audio_url': song.audio_url,
        'album_name': song.album_name,
        'duration': song.duration,
        'source': song.source or 'youtube',
        'genre': song.genre,
        'region': song.region,
    }


def _is_playable_song(song: Song) -> bool:
    source = (song.source or '').lower()
    audio_url = song.audio_url or ''
    if source in {'db', 'test'} or 'example.com' in audio_url:
        return False
    if source == 'youtube':
        return bool(_YOUTUBE_ID_RE.match(str(song.id)))
    if source == 'search_cache':
        return bool(audio_url) or bool(_YOUTUBE_ID_RE.match(str(song.id)))
    if source in {'jamendo', 'nct', 'deezer_preview'}:
        return True
    return bool(audio_url)


def _playable_results(qs, limit: int) -> list[dict]:
    results = []
    for song in qs[:limit * 5]:
        if not _is_playable_song(song):
            continue
        results.append(_song_to_search_result(song))
        if len(results) >= limit:
            break
    return results


def _dedupe_results(results: list[dict], limit: int | None = None) -> list[dict]:
    seen = set()
    deduped = []
    for r in results:
        key = r.get('id') or (_normalize(r.get('title', '')), _normalize(r.get('subtitle', '')))
        if key not in seen and r.get('title'):
            seen.add(key)
            deduped.append(r)
            if limit and len(deduped) >= limit:
                break
    return deduped


def _db_search_results(query: str, limit: int) -> list[dict]:
    terms = [term for term in re.split(r'\s+', query.strip()) if len(term) >= 2]
    token_query = Q()
    for term in terms:
        token_query |= Q(title__icontains=term) | Q(subtitle__icontains=term) | Q(album_name__icontains=term)
    query_filter = token_query or (
        Q(title__icontains=query)
        | Q(subtitle__icontains=query)
        | Q(album_name__icontains=query)
    )
    return _playable_results(Song.objects.filter(query_filter).order_by('-created_at'), limit)


def _db_genre_results(genre: str, limit: int) -> list[dict]:
    return _playable_results(Song.objects.filter(genre__iexact=genre).order_by('-created_at'), limit)


def _db_region_results(region: str, limit: int) -> list[dict]:
    normalized = region.replace('-', ' ')
    return _playable_results(
        Song.objects.filter(
            Q(region__iexact=region)
            | Q(region__iexact=normalized)
            | Q(genre__iexact=region)
            | Q(genre__iexact=normalized)
        ).order_by('-created_at'),
        limit,
    )


def _db_recent_results(limit: int) -> list[dict]:
    return _playable_results(Song.objects.order_by('-created_at'), limit)


def _db_genres_map(genres: list[str], per_limit: int) -> dict[str, list[dict]]:
    wanted = {genre.lower(): genre for genre in genres}
    grouped = {genre: [] for genre in genres}
    for song in Song.objects.filter(genre__isnull=False).order_by('-created_at')[:300]:
        if not _is_playable_song(song):
            continue
        key = (song.genre or '').lower()
        genre = wanted.get(key)
        if genre and len(grouped[genre]) < per_limit:
            grouped[genre].append(_song_to_search_result(song))
    return grouped


def _merge_db_first(db_results: list[dict], external_results: list[dict], limit: int) -> list[dict]:
    return _dedupe_results([*db_results, *external_results], limit)


def _can_call_jamendo() -> bool:
    return bool(settings.JAMENDO_CLIENT_ID)


def _include_total(request) -> bool:
    return request.query_params.get('return_total', 'true').lower() not in {'0', 'false', 'no'}


def _cached_count(key: str, qs, timeout: int = 30) -> int:
    cached = cache.get(key)
    if cached is not None:
        return cached
    count = qs.count()
    cache.set(key, count, timeout=timeout)
    return count


def _clear_user_count_cache(user_id: str):
    for prefix in ('history-count', 'favorites-count', 'downloads-count'):
        cache.delete(f'{prefix}:{user_id}')


def _user_list_version(user_id: str, list_name: str) -> int:
    return cache.get(f'{list_name}-version:{user_id}') or 1


def _bump_user_list_version(user_id: str, list_name: str):
    key = f'{list_name}-version:{user_id}'
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 2, timeout=None)


class ResolveAudioView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ResolveAudioSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        video_id = data.get('video_id') or data.get('youtube_id')
        resolve_cache_key = _cache_key(
            'resolve:v2',
            video_id or '',
            data.get('nct_url') or '',
            data.get('title') or '',
            data.get('artist') or '',
        )
        cached = cache.get(resolve_cache_key)
        if cached:
            return Response(cached)

        if video_id:
            try:
                result = extract_audio_url(video_id)
                response = {
                    'youtube_id': video_id,
                    'audio_url': result['audio_url'],
                    'expires_at': result['expires_at'],
                    'title': result.get('title'),
                    'duration': result.get('duration'),
                }
                cache.set(resolve_cache_key, response, timeout=3600)
                return Response(response)
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
            response = {
                'audio_url': result['audio_url'],
                'source': 'nct',
            }
            cache.set(resolve_cache_key, response, timeout=3600)
            return Response(response)

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
                response = {
                    'youtube_id': yt_data['id'],
                    'audio_url': audio['audio_url'],
                    'expires_at': audio['expires_at'],
                    'title': audio.get('title', title),
                    'duration': audio.get('duration'),
                }
                cache.set(resolve_cache_key, response, timeout=3600)
                return Response(response)
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
        premium = _is_premium_cached(str(request.user.id))
        cache_key = _cache_key('search:v5', query.strip().lower(), limit, params['sources'], premium)
        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

        db_results = _db_search_results(query, limit)
        if db_results:
            deduped = _dedupe_results(db_results, limit)
            truncated = False
            if not premium:
                truncated = len(deduped) > FREE_SEARCH_LIMIT
                deduped = deduped[:FREE_SEARCH_LIMIT]
            response = {
                'results': deduped[:limit],
                'total': len(deduped),
                'truncated': truncated,
                'errors': None,
            }
            cache.set(cache_key, response, timeout=300)
            return Response(response)

        futures = {}
        errors = []

        with ThreadPoolExecutor(max_workers=3) as ex:
            if 'youtube' in sources:
                futures['youtube'] = ex.submit(search_youtube, query, limit)
            if 'jamendo' in sources:
                futures['jamendo'] = ex.submit(jamendo_search, query, limit)
            if 'nct' in sources:
                futures['nct'] = ex.submit(nct_search, query, limit)

        external_results = []
        for name, future in futures.items():
            try:
                external_results.extend(future.result())
            except YouTubeError as e:
                errors.append(f'youtube: {e}')
            except JamendoError as e:
                errors.append(f'jamendo: {e}')
            except Exception:
                errors.append(f'{name}: failed')

        if external_results:
            Thread(target=_background_save_results, args=(external_results,), daemon=True).start()

        deduped = _merge_db_first(db_results, external_results, limit)

        truncated = False
        if not premium:
            truncated = len(deduped) > FREE_SEARCH_LIMIT
            deduped = deduped[:FREE_SEARCH_LIMIT]

        response = {
            'results': deduped[:limit],
            'total': len(deduped),
            'truncated': truncated,
            'errors': errors if errors else None,
        }
        cache.set(cache_key, response, timeout=300)
        return Response(response)


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
        premium = _is_premium_cached(str(request.user.id))
        cache_key = f'home_feed:{"premium" if premium else "free"}:v4'
        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

        genres = {}
        genre_slugs = ['rock', 'pop', 'hip-hop', 'electronic', 'jazz', 'folk']
        db_genres = _db_genres_map(genre_slugs, 10)
        for genre in genre_slugs:
            db_tracks = db_genres.get(genre, [])
            external_tracks = []
            try:
                if not db_tracks and _can_call_jamendo():
                    external_tracks = jamendo_genre(genre, 10)
            except JamendoError:
                external_tracks = []
            genres[genre] = _merge_db_first(db_tracks, external_tracks, 10)

        trending = _db_recent_results(20)
        try:
            if not trending and _can_call_jamendo():
                trending = jamendo_discovery(20)
        except JamendoError:
            pass

        if not premium:
            feed = {
                'trending': trending,
                'genres': genres,
            }
            cache.set(cache_key, feed, timeout=1800)
            return Response(feed)

        charts = {}
        chart_regions = ['v-pop', 'us-uk', 'k-pop', 'v-rap', 'billboard']
        for region in chart_regions:
            db_tracks = _db_region_results(region, 20)
            external_tracks = []
            try:
                if not db_tracks:
                    external_tracks = nct_get_chart(region)
            except Exception:
                external_tracks = []
            charts[region] = _merge_db_first(db_tracks, external_tracks, 20)

        feed = {
            'trending': trending,
            'charts': charts,
            'genres': genres,
        }

        cache.set(cache_key, feed, timeout=1800)
        return Response(feed)


class ChartDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _is_premium_cached(str(request.user.id)):
            return Response(
                {'detail': 'Charts are a Premium feature. Upgrade to access full chart details.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        region = request.query_params.get('region', '')
        if not region:
            return Response({'detail': 'region parameter is required'}, status=status.HTTP_400_BAD_REQUEST)
        cache_key = _cache_key('chart:v2', region.lower().strip())
        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

        db_tracks = _db_region_results(region, 20)
        external_tracks = nct_get_chart(region) if not db_tracks else []
        tracks = _merge_db_first(db_tracks, external_tracks, 20)
        response = {'region': region, 'tracks': tracks}
        cache.set(cache_key, response, timeout=1800)
        return Response(response)


class GenreTrackListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        genre = request.query_params.get('genre', '')
        if not genre:
            return Response({'detail': 'genre parameter is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            premium = _is_premium_cached(str(request.user.id))
            limit = 20 if premium else 10
            cache_key = _cache_key('genre:v2', genre.lower().strip(), limit)
            cached = cache.get(cache_key)
            if cached:
                return Response(cached)
            db_tracks = _db_genre_results(genre, limit)
            external_tracks = jamendo_genre(genre, limit) if not db_tracks and _can_call_jamendo() else []
            tracks = _merge_db_first(db_tracks, external_tracks, limit)
            response = {
                'genre': genre,
                'tracks': tracks,
                'truncated': not premium and len(tracks) >= limit,
            }
            cache.set(cache_key, response, timeout=1800)
            return Response(response)
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

        now = timezone.now()
        if connection.vendor == 'postgresql':
            with connection.cursor() as cursor:
                cursor.execute(
                    '''
                    INSERT INTO play_history (user_id, song_id, count, last_played)
                    VALUES (%s, %s, 1, %s)
                    ON CONFLICT (user_id, song_id)
                    DO UPDATE SET count = play_history.count + 1, last_played = EXCLUDED.last_played
                    RETURNING count
                    ''',
                    [str(request.user.id), song_id, now],
                )
                count = cursor.fetchone()[0]
        else:
            history, created = PlayHistory.objects.get_or_create(
                user=request.user,
                song_id=song_id,
                defaults={'count': 1, 'last_played': now},
            )
            if created:
                count = history.count
            else:
                PlayHistory.objects.filter(pk=history.pk).update(
                    count=F('count') + 1,
                    last_played=now,
                )
                history.refresh_from_db()
                count = history.count
        cache.delete(f'history-count:{request.user.id}')
        cache.delete(f'user-stats:{request.user.id}')
        _bump_user_list_version(str(request.user.id), 'history')

        return Response({'detail': 'Play recorded', 'count': count})


class PlayHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        offset = int(request.query_params.get('offset', 0))
        limit = int(request.query_params.get('limit', 20))

        qs = PlayHistory.objects.filter(user=request.user)\
            .select_related('song')\
            .order_by('-last_played')

        if not _is_premium_cached(str(request.user.id)):
            cutoff = timezone.now() - timedelta(days=FREE_HISTORY_DAYS)
            qs = qs.filter(last_played__gte=cutoff)

        cache_key = _cache_key(
            'history-page:v1',
            request.user.id,
            _user_list_version(str(request.user.id), 'history'),
            offset,
            limit,
            _include_total(request),
        )
        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

        total = _cached_count(f'history-count:{request.user.id}', qs) if _include_total(request) else None

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

        response = {'history': history, 'total': total}
        cache.set(cache_key, response, timeout=60)
        return Response(response)

    def delete(self, request):
        song_id = request.query_params.get('song_id')
        qs = PlayHistory.objects.filter(user=request.user)

        if song_id:
            deleted, _ = qs.filter(song_id=song_id).delete()
            if deleted == 0:
                return Response({'detail': 'History entry not found'}, status=status.HTTP_404_NOT_FOUND)
            cache.delete(f'history-count:{request.user.id}')
            cache.delete(f'user-stats:{request.user.id}')
            _bump_user_list_version(str(request.user.id), 'history')
            return Response({'detail': 'History entry deleted'})
        else:
            qs.delete()
            cache.delete(f'history-count:{request.user.id}')
            cache.delete(f'user-stats:{request.user.id}')
            _bump_user_list_version(str(request.user.id), 'history')
            return Response({'detail': 'All history cleared'})


class TopPlayedView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        limit = int(request.query_params.get('limit', 10))

        qs = PlayHistory.objects.filter(user=request.user)\
            .select_related('song')\
            .order_by('-count')

        if not _is_premium_cached(str(request.user.id)):
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
            if not _is_premium_cached(str(request.user.id)):
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
            cache.delete(f'favorites-count:{request.user.id}')
            cache.delete(f'user-stats:{request.user.id}')
            _bump_user_list_version(str(request.user.id), 'favorites')
            return Response({'detail': 'Added to favorites', 'liked': True})
        else:
            LikedSong.objects.filter(user=request.user, song_id=song_id).delete()
            cache.delete(f'favorites-count:{request.user.id}')
            cache.delete(f'user-stats:{request.user.id}')
            _bump_user_list_version(str(request.user.id), 'favorites')
            return Response({'detail': 'Removed from favorites', 'liked': False})


class FavoriteListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        offset = int(request.query_params.get('offset', 0))
        limit = int(request.query_params.get('limit', 20))

        qs = LikedSong.objects.filter(user=request.user)\
            .select_related('song')\
            .order_by('-liked_at')
        cache_key = _cache_key(
            'favorites-page:v1',
            request.user.id,
            _user_list_version(str(request.user.id), 'favorites'),
            offset,
            limit,
            _include_total(request),
        )
        cached = cache.get(cache_key)
        if cached:
            return Response(cached)
        total = _cached_count(f'favorites-count:{request.user.id}', qs) if _include_total(request) else None

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

        response = {'favorites': favorites, 'total': total}
        cache.set(cache_key, response, timeout=60)
        return Response(response)


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

        if not _is_premium_cached(str(request.user.id)):
            current_count = DownloadedSong.objects.filter(user=request.user).count()
            if current_count >= FREE_DOWNLOAD_LIMIT:
                return Response(
                    {'detail': f'Download limit reached ({FREE_DOWNLOAD_LIMIT}). Upgrade to Premium for unlimited downloads.'},
                    status=status.HTTP_403_FORBIDDEN,
                )

        downloaded = DownloadedSong.objects.create(user=request.user, song_id=song_id)
        cache.delete(f'downloads-count:{request.user.id}')
        _bump_user_list_version(str(request.user.id), 'downloads')
        return Response(
            {'detail': 'Song downloaded', 'downloaded_at': downloaded.downloaded_at},
            status=status.HTTP_201_CREATED,
        )

    def delete(self, request, song_id):
        deleted, _ = DownloadedSong.objects.filter(user=request.user, song_id=song_id).delete()
        if deleted == 0:
            return Response({'detail': 'Downloaded song not found'}, status=status.HTTP_404_NOT_FOUND)
        cache.delete(f'downloads-count:{request.user.id}')
        _bump_user_list_version(str(request.user.id), 'downloads')
        return Response({'detail': 'Download removed'}, status=status.HTTP_200_OK)


class DownloadedSongsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        offset = int(request.query_params.get('offset', 0))
        limit = int(request.query_params.get('limit', 20))

        qs = DownloadedSong.objects.filter(user=request.user)\
            .select_related('song')\
            .order_by('-downloaded_at')
        cache_key = _cache_key(
            'downloads-page:v1',
            request.user.id,
            _user_list_version(str(request.user.id), 'downloads'),
            offset,
            limit,
            _include_total(request),
        )
        cached = cache.get(cache_key)
        if cached:
            return Response(cached)
        total = _cached_count(f'downloads-count:{request.user.id}', qs) if _include_total(request) else None

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

        response = {'downloads': downloads, 'total': total}
        cache.set(cache_key, response, timeout=60)
        return Response(response)


class RelatedView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, song_id):
        limit = int(request.query_params.get('limit', 10))
        cache_key = _cache_key('related:v2', song_id, limit)
        cached = cache.get(cache_key)
        if cached:
            return Response(cached)
        song = Song.objects.filter(id=song_id).first()
        db_results = []

        if song and song.title:
            db_results = _db_search_results(f'{song.title} {song.subtitle or ""}', limit + 1)
            db_results = [r for r in db_results if r['id'] != song_id]
            if db_results:
                results = _dedupe_results(db_results, limit)
                response = {'results': results, 'total': len(results)}
                cache.set(cache_key, response, timeout=1800)
                return Response(response)

        external_results = []

        try:
            if _YOUTUBE_ID_RE.match(song_id):
                external_results = get_related_videos(song_id, limit)
            elif song and song.title:
                external_results = search_youtube(f'{song.title} {song.subtitle or ""}', limit)
        except YouTubeError:
            external_results = []

        results = _merge_db_first(db_results, external_results, limit)

        response = {
            'results': results,
            'total': len(results),
        }
        cache.set(cache_key, response, timeout=1800)
        return Response(response)


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
        premium = _is_premium_cached(str(request.user.id))
        current_count = _cached_count(
            f'downloads-count:{request.user.id}',
            DownloadedSong.objects.filter(user=request.user),
        )

        return Response({
            'is_premium': premium,
            'downloads_used': current_count,
            'downloads_limit': None if premium else FREE_DOWNLOAD_LIMIT,
        })
