import re
from typing import Optional
import httpx
from django.core.cache import cache
from bs4 import BeautifulSoup


NCT_CACHE_TTL = 3600


def _ck(key: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_:.-]', '_', key)
NCT_BASE = 'https://www.nhaccuatui.com'


class NCTError(Exception):
    pass


def _fetch_html(url: str) -> str:
    try:
        resp = httpx.get(url, timeout=10, follow_redirects=True,
                         headers={'User-Agent': 'Mozilla/5.0'})
        resp.raise_for_status()
        return resp.text
    except httpx.HTTPError as e:
        raise NCTError(f'NCT request failed: {e}') from e


def _parse_track_from_li(li) -> Optional[dict]:
    try:
        title_el = li.select_one('.name_song a')
        artist_el = li.select_one('.name_artist a')
        img_el = li.select_one('img')
        link_el = li.select_one('a[data-url], a[href]')

        if not title_el:
            return None

        title = title_el.get_text(strip=True)
        artist = artist_el.get_text(strip=True) if artist_el else ''
        img = img_el.get('src', '') if img_el else ''
        song_url = link_el.get('href', '') if link_el else ''

        return {
            'id': song_url,
            'title': title,
            'subtitle': artist,
            'image_url': img,
            'audio_url': None,
            'duration': None,
            'source': 'nct',
        }
    except Exception:
        return None


def search(query: str, limit: int = 10) -> list:
    cache_key = _ck(f'nct_search:{query}:{limit}')
    cached = cache.get(cache_key)
    if cached:
        return cached

    try:
        html = _fetch_html(f'{NCT_BASE}/ajax/search?q={query}')
        data = re.search(r'<!--(.*?)-->', html, re.DOTALL)
        if not data:
            return []
        import json
        try:
            results = json.loads(data.group(1).strip())
        except json.JSONDecodeError:
            return []

        tracks = []
        for item in results.get('songs', [])[:limit]:
            tracks.append({
                'id': item.get('url', ''),
                'title': item.get('title', ''),
                'subtitle': item.get('artist', ''),
                'image_url': item.get('thumbnail', ''),
                'audio_url': None,
                'duration': item.get('duration'),
                'source': 'nct',
            })
        cache.set(cache_key, tracks, timeout=NCT_CACHE_TTL)
        return tracks
    except NCTError:
        return []


def get_chart(region: str) -> list:
    region_slugs = {
        'v-pop': 'v-pop',
        'vpop': 'v-pop',
        'us-uk': 'us-uk',
        'usuk': 'us-uk',
        'k-pop': 'k-pop',
        'kpop': 'k-pop',
        'v-rap': 'v-rap',
        'vrap': 'v-rap',
        'billboard': 'billboard',
    }
    slug = region_slugs.get(region.lower().strip())
    if not slug:
        return []

    cache_key = _ck(f'nct_chart:{slug}')
    cached = cache.get(cache_key)
    if cached:
        return cached

    try:
        html = _fetch_html(f'{NCT_BASE}/chart/{slug}')
        try:
            soup = BeautifulSoup(html, 'lxml')
        except Exception:
            soup = BeautifulSoup(html, 'html.parser')
        tracks = []
        for li in soup.select('ul.list_music li.item_music'):
            track = _parse_track_from_li(li)
            if track:
                track['region'] = region
                tracks.append(track)
            if len(tracks) >= 20:
                break

        cache.set(cache_key, tracks, timeout=NCT_CACHE_TTL)
        return tracks
    except Exception:
        return []


_NCT_KEY_RE = re.compile(r'(?:/|\.)([A-Za-z0-9]{10,})(?:\.html)?$')


def _resolve_nuxt_field(data, idx):
    while isinstance(idx, int) and idx < len(data):
        val = data[idx]
        if isinstance(val, int) and val != idx:
            idx = val
        else:
            return val
    return idx


def resolve_audio(nct_url: str) -> Optional[dict]:
    match = _NCT_KEY_RE.search(nct_url)
    if not match:
        return None
    key = match.group(1)

    cache_key = _ck(f'nct_audio:{key}')
    cached = cache.get(cache_key)
    if cached:
        return cached

    try:
        html = _fetch_html(nct_url)
    except NCTError:
        return None

    import json

    for m in re.finditer(r'<script[^>]*>([^<]+)</script>', html):
        text = m.group(1).strip()
        if text.startswith('[[') and 'ShallowReactive' in text:
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            pinia = payload[3]
            song_idx = pinia.get(f'dataDetail:{key}')
            if not isinstance(song_idx, int) or song_idx >= len(payload):
                continue
            song = _resolve_nuxt_field(payload, song_idx)
            if not isinstance(song, dict):
                continue
            sr_ref = song.get('streamURL')
            sr_list = _resolve_nuxt_field(payload, sr_ref)
            if not isinstance(sr_list, list):
                continue

            best = None
            for ref in sr_list:
                stream = _resolve_nuxt_field(payload, ref)
                if not isinstance(stream, dict):
                    continue
                vip = stream.get('onlyVIP', True)
                if isinstance(vip, int):
                    vip_val = payload[vip] if vip < len(payload) else True
                    vip = bool(vip_val) if not isinstance(vip_val, bool) else vip_val
                if vip:
                    continue
                stream_url_ref = stream.get('stream')
                stream_url = _resolve_nuxt_field(payload, stream_url_ref)
                if not isinstance(stream_url, str) or not stream_url:
                    continue
                quality_ref = stream.get('type')
                quality = _resolve_nuxt_field(payload, quality_ref) if isinstance(quality_ref, int) else quality_ref
                try:
                    q = int(quality)
                except (TypeError, ValueError):
                    q = 0
                if best is None or q > best['quality']:
                    best = {'url': stream_url, 'quality': q}

            if best:
                result = {'audio_url': best['url'], 'quality': best['quality']}
                cache.set(cache_key, result, timeout=NCT_CACHE_TTL)
                return result

    return None


def health_check() -> bool:
    try:
        _fetch_html(NCT_BASE)
        return True
    except NCTError:
        return False
