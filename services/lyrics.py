import re

import httpx
import yt_dlp
from django.core.cache import cache

from music.models import Lyric


def fetch_and_store_lyrics(song_id):
    if not re.match(r'^[A-Za-z0-9_-]{11}$', song_id):
        return None

    cache_key = f'lyrics:attempt:{song_id}'
    if cache.get(cache_key):
        return None

    captions = _fetch_youtube_captions(song_id)
    if not captions:
        cache.set(cache_key, True, timeout=3600)
        return None

    lyric, _ = Lyric.objects.update_or_create(
        song_id=song_id,
        defaults={
            'plain': captions['plain'],
            'synced': captions.get('synced'),
            'source': 'youtube_captions',
        },
    )
    return lyric


def _fetch_youtube_captions(video_id):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
    }

    try:
        url = f'https://www.youtube.com/watch?v={video_id}'
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:
        return None

    subtitles = info.get('subtitles') or {}
    auto_captions = info.get('automatic_captions') or {}

    for src in (subtitles, auto_captions):
        for lang in ('en', 'vi', 'en-US', 'en-GB', 'original'):
            entries = src.get(lang) or src.get(lang.lower())
            if entries:
                captions = _download_vtt(entries)
                if captions:
                    return captions

    for src in (subtitles, auto_captions):
        for lang, entries in src.items():
            if lang not in ('live_chat', 'live_chat_asr'):
                captions = _download_vtt(entries)
                if captions:
                    return captions

    return None


def _download_vtt(subtitle_entries):
    url = None
    for entry in subtitle_entries:
        if isinstance(entry, dict) and entry.get('ext') in ('vtt', 'json3', 'srv3', 'srv2', 'srv1'):
            url = entry['url']
            break
    if not url:
        for entry in subtitle_entries:
            if isinstance(entry, dict) and entry.get('url'):
                url = entry['url']
                break
    if not url:
        return None

    try:
        resp = httpx.get(url, timeout=15, follow_redirects=True)
        resp.raise_for_status()
        return _parse_vtt(resp.text)
    except Exception:
        return None


def _parse_vtt(vtt_text):
    text = vtt_text.strip()
    if not text:
        return None

    is_json = text.startswith('{')
    if is_json:
        return _parse_json3(text)

    lines = text.split('\n')
    plain_parts = []
    lrc_parts = []
    current_start = None
    current_text = []

    start = 0
    for i, line in enumerate(lines):
        if line.strip() == '':
            start = i + 1
            break

    for line in lines[start:]:
        line = line.strip()
        if not line:
            continue
        if line.startswith('NOTE') or line.startswith('STYLE'):
            continue

        m = re.match(
            r'(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})\.(\d{3})',
            line,
        )
        if m:
            if current_start is not None and current_text:
                lrc = _to_lrc(current_start, ' '.join(current_text))
                if lrc:
                    lrc_parts.append(lrc)
                plain_parts.extend(current_text)

            h, mi, s, ms = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
            current_start = h * 60 + mi + s / 60 + ms / 60000
            current_text = []
        elif current_start is not None:
            clean = re.sub(r'<[^>]+>', '', line)
            clean = re.sub(r'^\s*>>\s*', '', clean)
            if clean:
                current_text.append(clean)

    if current_start is not None and current_text:
        lrc = _to_lrc(current_start, ' '.join(current_text))
        if lrc:
            lrc_parts.append(lrc)
        plain_parts.extend(current_text)

    plain = '\n'.join(plain_parts).strip()
    synced = '\n'.join(lrc_parts).strip()

    if not plain:
        return None
    return {'plain': plain, 'synced': synced or None}


def _parse_json3(json_text):
    import json
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        return None

    events = data.get('events', [])
    plain_parts = []
    lrc_parts = []

    for ev in events:
        t_start = ev.get('tStartMs', 0)
        segs = ev.get('segs', [])
        text = ''.join(s.get('utf8', '') for s in segs if isinstance(s, dict))
        text = text.strip()
        if not text:
            continue
        plain_parts.append(text)

        minutes = t_start / 60000
        lrc = _to_lrc(minutes, text)
        if lrc:
            lrc_parts.append(lrc)

    plain = '\n'.join(plain_parts).strip()
    synced = '\n'.join(lrc_parts).strip()

    if not plain:
        return None
    return {'plain': plain, 'synced': synced or None}


def _to_lrc(minutes, text):
    m = int(minutes)
    s = int((minutes - m) * 60)
    cs = int(((minutes - m) * 60 - s) * 100)
    return f'[{m:02d}:{s:02d}.{cs:02d}]{text}'
