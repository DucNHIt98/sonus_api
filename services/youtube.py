from typing import Optional
import yt_dlp
from django.core.cache import cache


YT_CACHE_TTL = 14400
YT_SEARCH_CACHE_TTL = 3600


class YouTubeError(Exception):
    pass


def extract_audio_url(video_id: str) -> dict:
    cache_key = f'yt_audio:{video_id}'
    cached = cache.get(cache_key)
    if cached:
        return cached

    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
    }
    url = f'https://www.youtube.com/watch?v={video_id}'
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        raise YouTubeError(f'Failed to extract audio: {e}') from e

    result = {
        'audio_url': info.get('url'),
        'expires_at': YT_CACHE_TTL,
        'title': info.get('title'),
        'duration': info.get('duration'),
        'thumbnail': info.get('thumbnail'),
    }
    cache.set(cache_key, result, timeout=YT_CACHE_TTL)
    return result


def search_youtube(query: str, limit: int = 10) -> list:
    cache_key = f'yt_search:{query}:{limit}'
    cached = cache.get(cache_key)
    if cached:
        return cached

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': 'in_playlist',
        'force_generic_extractor': False,
    }
    search_query = f'ytsearch{limit}:{query}'
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_query, download=False)
    except Exception as e:
        raise YouTubeError(f'Search failed: {e}') from e

    results = []
    for entry in info.get('entries', []):
        if not entry:
            continue
        video_id = entry.get('id')
        if not video_id:
            continue
        results.append({
            'id': video_id,
            'title': entry.get('title', ''),
            'subtitle': entry.get('channel', '') or entry.get('uploader', ''),
            'image_url': entry.get('thumbnail', ''),
            'duration': entry.get('duration'),
            'source': 'youtube',
            'audio_url': None,
        })

    cache.set(cache_key, results, timeout=YT_SEARCH_CACHE_TTL)
    return results


def get_autocomplete(query: str) -> list:
    cache_key = f'yt_ac:{query}'
    cached = cache.get(cache_key)
    if cached:
        return cached

    import httpx
    import json as _json
    try:
        resp = httpx.get(
            'https://suggestqueries.google.com/complete/search',
            params={'client': 'youtube', 'ds': 'yt', 'q': query},
            timeout=5,
        )
        resp.raise_for_status()
        text = resp.text
        if text.startswith('window.google.ac.h('):
            text = text[len('window.google.ac.h('):-1]
        data = _json.loads(text)
        suggestions = data[1] if len(data) > 1 else []
        suggestions = [s[0] for s in suggestions if isinstance(s, list) and len(s) > 0]
    except Exception:
        suggestions = []

    cache.set(cache_key, suggestions, timeout=YT_SEARCH_CACHE_TTL)
    return suggestions


def search_youtube_best(query: str) -> Optional[dict]:
    results = search_youtube(query, limit=5)
    if not results:
        return None

    for r in results:
        if r.get('duration') and r['duration'] <= 600:
            return r
    return results[0]


def convert_deezer_to_youtube(title: str, artist: str) -> Optional[dict]:
    query = f'{artist} - {title} official'
    result = search_youtube_best(query)
    if result:
        return result
    return search_youtube_best(f'{artist} {title}')


def get_related_videos(video_id: str, limit: int = 10) -> list:
    cache_key = f'yt_related:{video_id}:{limit}'
    cached = cache.get(cache_key)
    if cached:
        return cached

    title = ''
    try:
        info = _extract_video_info(video_id)
        title = info.get('title', '') if info else ''
        channel = info.get('channel', info.get('uploader', '')) if info else ''
    except YouTubeError:
        return search_suggestions(video_id, limit)

    if not title:
        return []

    query = f'{title} {channel}'
    results = search_youtube(query, limit)
    results = [r for r in results if r['id'] != video_id]

    cache.set(cache_key, results, timeout=YT_SEARCH_CACHE_TTL)
    return results


def search_suggestions(query: str, limit: int = 10) -> list:
    return search_youtube(query, limit)


def _extract_video_info(video_id: str) -> dict:
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
    }
    url = f'https://www.youtube.com/watch?v={video_id}'
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as e:
        raise YouTubeError(f'Failed to extract video info: {e}') from e
