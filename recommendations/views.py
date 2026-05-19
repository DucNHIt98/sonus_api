import logging
import re

from django.core.cache import cache
from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.responses import success, bad_request
from music.models import Song
from services.gemini_client import get_recommendations as gemini_recommend
from services.youtube import search_youtube_best, get_related_videos

logger = logging.getLogger(__name__)


def _normalize(value):
    """Chuẩn hóa chuỗi để so sánh dedup: bỏ ký tự đặc biệt, lowercase."""
    return ''.join(ch for ch in (value or '').lower() if ch.isalnum())


def _song_to_result(song: Song) -> dict:
    """Chuyển Song model thành dict response chuẩn cho recommendation feed."""
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
    """
    Tìm kiếm bài hát trong DB theo tiêu đề, nghệ sĩ, album.
    Tách query thành từng token (min 2 ký tự) để OR search linh hoạt hơn.
    Nếu không có token hợp lệ, fallback về full query search.
    Ưu tiên bài mới nhất (order_by -created_at).
    """
    terms = [term for term in re.split(r'\s+', query.strip()) if len(term) >= 2]
    query_filter = Q()
    for term in terms:
        query_filter |= Q(title__icontains=term) | Q(subtitle__icontains=term) | Q(album_name__icontains=term)
    if not query_filter:
        query_filter = Q(title__icontains=query) | Q(subtitle__icontains=query) | Q(album_name__icontains=query)
    duration_filter = Q(duration__gte=180, duration__lte=420)
    return [
        _song_to_result(song)
        for song in Song.objects.filter(query_filter & duration_filter).order_by('-created_at')[:limit]
    ]


def _dedupe(results: list[dict], limit: int) -> list[dict]:
    """
    Loại bỏ kết quả trùng lặp và bài hát không có title.
    Key dedup: id nếu có, hoặc tuple (normalized_title, normalized_subtitle).
    Dừng khi đủ limit để tránh xử lý không cần thiết.
    """
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
    """
    GET /recommendations/?song_id=xxx — Gợi ý bài hát tương tự.
    Chiến lược 3 tầng (theo thứ tự ưu tiên):
      1. DB-first: tìm trong nội bộ theo title+artist (nhanh, không phụ thuộc API ngoài)
      2. Gemini AI: hỏi Gemini gợi ý bài tương tự → tìm mỗi gợi ý trong DB hoặc YouTube
      3. YouTube related: nếu Gemini không có gợi ý, lấy video liên quan từ YouTube API
    Cache 1 giờ để tránh gọi Gemini/YouTube lặp lại.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        song_id = request.query_params.get('song_id', '')
        song_title = request.query_params.get('title', '')
        song_artist = request.query_params.get('artist', '')

        if not song_id and not song_title:
            return bad_request('Provide song_id or title')

        cache_key = f'recommendations:v2:{song_id or f"{song_title}_{song_artist}"}'
        cached = cache.get(cache_key)
        if cached:
            return success(cached)

        if song_id:
            song = Song.objects.filter(id=song_id).first()
            title = song.title if song else song_id
            artist = song.subtitle if song else ''
            video_id = song_id
        else:
            title = song_title
            artist = song_artist
            video_id = None

        # Tầng 1: tìm trong DB — loại bỏ chính bài đang phát
        db_first = _db_search(f'{title} {artist}', 10)
        db_first = [r for r in db_first if r['id'] != song_id]
        if db_first:
            data = {'recommendations': _dedupe(db_first, 10)}
            cache.set(cache_key, data, timeout=3600)
            return success(data)

        # Tầng 2: Gemini AI gợi ý → tìm mỗi gợi ý trong DB, nếu không có thì YouTube search
        suggestions = []
        try:
            suggestions = gemini_recommend(title, artist) or []
        except Exception:
            logger.warning('Gemini recommend failed for "%s - %s"', title, artist, exc_info=True)

        results = []

        if suggestions:
            for rec in suggestions[:5]:
                query = f'{rec["title"]} {rec["artist"]}'
                db_match = _db_search(query, 1)
                if db_match:
                    results.extend(db_match)
                    continue
                try:
                    yt = search_youtube_best(query)
                except Exception:
                    logger.warning('YouTube search failed for recommendation query "%s"', query, exc_info=True)
                    yt = None
                if yt:
                    results.append({
                        'id': yt['id'],
                        'title': yt.get('title', rec['title']),
                        'subtitle': yt.get('subtitle', rec['artist']),
                        'image_url': yt.get('image_url', ''),
                        'duration': yt.get('duration'),
                        'source': 'youtube',
                        'audio_url': None,  # Cần resolve riêng khi play
                    })
        elif video_id:
            # Tầng 3: YouTube related videos khi không có Gemini suggestions
            db_related = _db_search(f'{title} {artist}', 11)
            db_related = [r for r in db_related if r['id'] != song_id]
            remaining = max(10 - len(db_related), 0)
            if remaining:
                try:
                    external = get_related_videos(video_id, remaining)
                except Exception:
                    logger.warning('YouTube related videos failed for song_id %s', video_id, exc_info=True)
                    external = []
            else:
                external = []
            results = [*db_related, *external]

        data = {'recommendations': _dedupe(results, 10)}
        cache.set(cache_key, data, timeout=3600)
        return success(data)
