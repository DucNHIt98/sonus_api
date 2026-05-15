from django.core.cache import cache
from django.db import connection
from django.db.models import F
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from services.nct import get_chart as nct_get_chart, search as nct_search
from services.jamendo import JamendoError
from services.jamendo import search as jamendo_search
from services.jamendo import get_tracks_by_genre as jamendo_genre
from services.jamendo import get_discovery as jamendo_discovery
from services.youtube import YouTubeError, extract_audio_url, search_youtube, get_autocomplete
from services.youtube import convert_deezer_to_youtube

from .models import Song, PlayHistory, LikedSong
from .serializers import (
    ResolveAudioSerializer,
    SearchSerializer,
    RecordPlaySerializer,
    PlayHistorySerializer,
    LikedSongSerializer,
)


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

        results = []
        errors = []

        if 'youtube' in sources:
            try:
                yt_results = search_youtube(query, limit)
                results.extend(yt_results)
            except YouTubeError as e:
                errors.append(f'youtube: {e}')

        if 'jamendo' in sources:
            try:
                jam_results = jamendo_search(query, limit)
                results.extend(jam_results)
            except JamendoError as e:
                errors.append(f'jamendo: {e}')

        if 'nct' in sources:
            try:
                nct_results = nct_search(query, limit)
                results.extend(nct_results)
            except Exception:
                errors.append('nct: failed')

        seen = set()
        deduped = []
        for r in results:
            key = (r.get('title', '').lower(), r.get('subtitle', '').lower())
            if key not in seen and r.get('title'):
                seen.add(key)
                deduped.append(r)

        return Response({
            'results': deduped[:limit],
            'total': len(deduped),
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

        cache.set(cache_key, feed, timeout=1800)
        return Response(feed)


class ChartDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        region = request.query_params.get('region', '')
        if not region:
            return Response({'detail': 'region parameter is required'}, status=status.HTTP_400_BAD_REQUEST)

        tracks = nct_get_chart(region)
        return Response({'region': region, 'tracks': tracks})


class GenreTrackListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
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
        user_id = str(request.user.id)

        title = data.get('title', '')
        subtitle = data.get('subtitle', '')
        image_url = data.get('image_url', '')
        duration = data.get('duration')

        with connection.cursor() as cursor:
            cursor.execute(
                'INSERT INTO songs (id, title, subtitle, image_url, duration, source) '
                'VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING',
                [song_id, title, subtitle, image_url, duration, 'youtube'],
            )

            cursor.execute(
                'SELECT count FROM play_history WHERE user_id = %s AND song_id = %s',
                [user_id, song_id],
            )
            row = cursor.fetchone()
            if row:
                cursor.execute(
                    'UPDATE play_history SET count = count + 1, last_played = %s WHERE user_id = %s AND song_id = %s',
                    [timezone.now(), user_id, song_id],
                )
                final_count = row[0] + 1
            else:
                cursor.execute(
                    'INSERT INTO play_history (user_id, song_id, count, last_played) VALUES (%s, %s, 1, %s)',
                    [user_id, song_id, timezone.now()],
                )
                final_count = 1

        return Response({'detail': 'Play recorded', 'count': final_count})


class PlayHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        offset = int(request.query_params.get('offset', 0))
        limit = int(request.query_params.get('limit', 20))
        user_id = str(request.user.id)

        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT ph.count, ph.last_played, s.id, s.title, s.subtitle, s.image_url, s.audio_url, s.duration, s.source '
                'FROM play_history ph JOIN songs s ON s.id = ph.song_id '
                'WHERE ph.user_id = %s ORDER BY ph.last_played DESC OFFSET %s LIMIT %s',
                [user_id, offset, limit],
            )
            rows = cursor.fetchall()
            cursor.execute(
                'SELECT COUNT(*) FROM play_history WHERE user_id = %s',
                [user_id],
            )
            total = cursor.fetchone()[0]

        history = []
        for row in rows:
            history.append({
                'count': row[0],
                'last_played': row[1],
                'song': {
                    'id': row[2],
                    'title': row[3],
                    'subtitle': row[4],
                    'image_url': row[5],
                    'audio_url': row[6],
                    'duration': row[7],
                    'source': row[8],
                },
            })

        return Response({'history': history, 'total': total})

    def delete(self, request):
        user_id = str(request.user.id)
        song_id = request.query_params.get('song_id')

        with connection.cursor() as cursor:
            if song_id:
                cursor.execute(
                    'DELETE FROM play_history WHERE user_id = %s AND song_id = %s RETURNING id',
                    [user_id, song_id],
                )
                if not cursor.fetchone():
                    return Response({'detail': 'History entry not found'}, status=status.HTTP_404_NOT_FOUND)
                return Response({'detail': 'History entry deleted'})
            else:
                cursor.execute(
                    'DELETE FROM play_history WHERE user_id = %s',
                    [user_id],
                )
                return Response({'detail': 'All history cleared'})


class TopPlayedView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        limit = int(request.query_params.get('limit', 10))
        user_id = str(request.user.id)

        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT ph.count, ph.last_played, s.id, s.title, s.subtitle, s.image_url, s.audio_url, s.duration, s.source '
                'FROM play_history ph JOIN songs s ON s.id = ph.song_id '
                'WHERE ph.user_id = %s ORDER BY ph.count DESC LIMIT %s',
                [user_id, limit],
            )
            rows = cursor.fetchall()

        top = []
        for row in rows:
            top.append({
                'count': row[0],
                'last_played': row[1],
                'song': {
                    'id': row[2],
                    'title': row[3],
                    'subtitle': row[4],
                    'image_url': row[5],
                    'audio_url': row[6],
                    'duration': row[7],
                    'source': row[8],
                },
            })

        return Response({'top': top})


class FavoriteToggleView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, song_id):
        liked = request.data.get('liked', True)
        user_id = str(request.user.id)

        with connection.cursor() as cursor:
            if liked:
                cursor.execute(
                    'INSERT INTO liked_songs (user_id, song_id, liked_at) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING',
                    [user_id, song_id, timezone.now()],
                )
                return Response({'detail': 'Added to favorites', 'liked': True})
            else:
                cursor.execute(
                    'DELETE FROM liked_songs WHERE user_id = %s AND song_id = %s',
                    [user_id, song_id],
                )
                return Response({'detail': 'Removed from favorites', 'liked': False})


class FavoriteListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        offset = int(request.query_params.get('offset', 0))
        limit = int(request.query_params.get('limit', 20))
        user_id = str(request.user.id)

        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT ls.liked_at, s.id, s.title, s.subtitle, s.image_url, s.audio_url, s.duration, s.source '
                'FROM liked_songs ls JOIN songs s ON s.id = ls.song_id '
                'WHERE ls.user_id = %s ORDER BY ls.liked_at DESC OFFSET %s LIMIT %s',
                [user_id, offset, limit],
            )
            rows = cursor.fetchall()

            cursor.execute(
                'SELECT COUNT(*) FROM liked_songs WHERE user_id = %s',
                [user_id],
            )
            total = cursor.fetchone()[0]

        favorites = []
        for row in rows:
            favorites.append({
                'created_at': row[0],
                'song': {
                    'id': row[1],
                    'title': row[2],
                    'subtitle': row[3],
                    'image_url': row[4],
                    'audio_url': row[5],
                    'duration': row[6],
                    'source': row[7],
                },
            })

        return Response({'favorites': favorites, 'total': total})
