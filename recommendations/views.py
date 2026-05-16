from django.core.cache import cache
import re
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q

from music.models import Song
from services.gemini_client import get_recommendations as gemini_recommend
from services.youtube import search_youtube_best, get_related_videos


def _normalize(value):
    return ''.join(ch for ch in (value or '').lower() if ch.isalnum())


def _song_to_result(song: Song) -> dict:
    return {
        'id': song.id,
        'title': song.title or '',
        'subtitle': song.subtitle or '',
        'image_url': song.image_url or '',
        'audio_url': song.audio_url,
        'duration': song.duration,
        'source': song.source or 'youtube',
    }


def _db_search(query: str, limit: int) -> list[dict]:
    terms = [term for term in re.split(r'\s+', query.strip()) if len(term) >= 2]
    query_filter = Q()
    for term in terms:
        query_filter |= Q(title__icontains=term) | Q(subtitle__icontains=term) | Q(album_name__icontains=term)
    if not query_filter:
        query_filter = Q(title__icontains=query) | Q(subtitle__icontains=query) | Q(album_name__icontains=query)
    return [
        _song_to_result(song)
        for song in Song.objects.filter(query_filter).order_by('-created_at')[:limit]
    ]


def _dedupe(results: list[dict], limit: int) -> list[dict]:
    seen = set()
    deduped = []
    for r in results:
        key = r.get('id') or (_normalize(r.get('title')), _normalize(r.get('subtitle')))
        if key not in seen and r.get('title'):
            seen.add(key)
            deduped.append(r)
            if len(deduped) >= limit:
                break
    return deduped


class RecommendView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        song_id = request.query_params.get('song_id', '')
        song_title = request.query_params.get('title', '')
        song_artist = request.query_params.get('artist', '')

        if not song_id and not song_title:
            return Response({'detail': 'Provide song_id or title'}, status=status.HTTP_400_BAD_REQUEST)

        video_id = song_id
        cache_key = f'recommendations:v2:{song_id or f"{song_title}_{song_artist}"}'
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

        db_first = _db_search(f'{title} {artist}', 10)
        db_first = [r for r in db_first if r['id'] != song_id]
        if db_first:
            feed = {'recommendations': _dedupe(db_first, 10)}
            cache.set(cache_key, feed, timeout=3600)
            return Response(feed)

        # Try Gemini first, fall back to YouTube related
        suggestions = gemini_recommend(title, artist)
        results = []

        if suggestions:
            for rec in suggestions[:5]:
                query = f'{rec["title"]} {rec["artist"]}'
                db_match = _db_search(query, 1)
                if db_match:
                    results.extend(db_match)
                    continue
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
            db_related = _db_search(f'{title} {artist}', 11)
            db_related = [r for r in db_related if r['id'] != song_id]
            remaining = max(10 - len(db_related), 0)
            external = get_related_videos(video_id, remaining) if remaining else []
            results = [*db_related, *external]

        feed = {'recommendations': _dedupe(results, 10)}
        cache.set(cache_key, feed, timeout=3600)
        return Response(feed)
