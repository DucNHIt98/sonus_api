from django.core.cache import cache
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from music.models import Song
from services.gemini_client import get_recommendations as gemini_recommend
from services.youtube import search_youtube_best, get_related_videos


class RecommendView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        song_id = request.query_params.get('song_id', '')
        song_title = request.query_params.get('title', '')
        song_artist = request.query_params.get('artist', '')

        if not song_id and not song_title:
            return Response({'detail': 'Provide song_id or title'}, status=status.HTTP_400_BAD_REQUEST)

        video_id = song_id
        cache_key = f'recommendations:{song_id or f"{song_title}_{song_artist}"}'
        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

        if song_id:
            song = Song.objects.filter(id=song_id).first()
            title = song.title if song else song_id
            artist = song.subtitle if song else ''
            video_id = song_id
        else:
            title = song_title
            artist = song_artist
            video_id = None

        # Try Gemini first, fall back to YouTube related
        suggestions = gemini_recommend(title, artist)
        results = []

        if suggestions:
            for rec in suggestions[:5]:
                query = f'{rec["title"]} {rec["artist"]}'
                yt = search_youtube_best(query)
                if yt:
                    results.append({
                        'id': yt['id'],
                        'title': yt.get('title', rec['title']),
                        'subtitle': yt.get('subtitle', rec['artist']),
                        'image_url': yt.get('image_url', ''),
                        'duration': yt.get('duration'),
                        'source': 'youtube',
                        'audio_url': None,
                    })
        elif video_id:
            results = get_related_videos(video_id, 10)

        feed = {'recommendations': results}
        cache.set(cache_key, feed, timeout=3600)
        return Response(feed)
