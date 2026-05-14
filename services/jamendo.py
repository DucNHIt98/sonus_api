import httpx
from django.conf import settings
from django.core.cache import cache


JAMENDO_CACHE_TTL = 3600
JAMENDO_BASE = settings.JAMENDO_BASE_URL


class JamendoError(Exception):
    pass


def _get_client_id():
    client_id = settings.JAMENDO_CLIENT_ID
    if not client_id:
        raise JamendoError('JAMENDO_CLIENT_ID is not configured')
    return client_id


def _get(params: dict) -> dict:
    params['client_id'] = _get_client_id()
    params['format'] = 'json'
    try:
        resp = httpx.get(f'{JAMENDO_BASE}/tracks/', params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as e:
        raise JamendoError(f'Jamendo API error: {e}') from e


def _parse_track(item: dict) -> dict:
    return {
        'id': f'jamendo_{item["id"]}',
        'title': item.get('name', ''),
        'subtitle': item.get('artist_name', ''),
        'image_url': item.get('image', ''),
        'audio_url': (
            item.get('audio', '').replace('http://', 'https://')
            or f'https://api.jamendo.com/v3.0/tracks/file/?client_id={_get_client_id()}&id={item["id"]}&audioformat=mp31'
        ),
        'duration': item.get('duration'),
        'source': 'jamendo',
        'album_name': item.get('album_name'),
    }


def search(query: str, limit: int = 10) -> list:
    cache_key = f'jamendo_search:{query}:{limit}'
    cached = cache.get(cache_key)
    if cached:
        return cached

    data = _get({'search': query, 'limit': limit, 'order': 'popularity_total', 'include': 'musicinfo'})
    results = [_parse_track(item) for item in data.get('results', [])]
    cache.set(cache_key, results, timeout=JAMENDO_CACHE_TTL)
    return results


def get_tracks_by_genre(genre: str, limit: int = 20) -> list:
    cache_key = f'jamendo_genre:{genre}:{limit}'
    cached = cache.get(cache_key)
    if cached:
        return cached

    data = _get({
        'tags': genre,
        'limit': limit,
        'order': 'popularity_week',
        'include': 'musicinfo',
    })
    results = [_parse_track(item) for item in data.get('results', [])]
    cache.set(cache_key, results, timeout=JAMENDO_CACHE_TTL)
    return results


def get_discovery(limit: int = 20) -> list:
    cache_key = f'jamendo_discovery:{limit}'
    cached = cache.get(cache_key)
    if cached:
        return cached

    data = _get({'limit': limit, 'order': 'popularity_total', 'include': 'musicinfo'})
    results = [_parse_track(item) for item in data.get('results', [])]
    cache.set(cache_key, results, timeout=JAMENDO_CACHE_TTL)
    return results
