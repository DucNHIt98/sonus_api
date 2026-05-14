import json

import httpx
from django.conf import settings
from django.core.cache import cache

GEMINI_CACHE_TTL = 3600


class GeminiError(Exception):
    pass


def _call_gemini(prompt: str) -> str:
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        raise GeminiError('GEMINI_API_KEY is not configured')

    url = (
        f'https://generativelanguage.googleapis.com/v1beta/models/'
        f'gemini-2.0-flash:generateContent?key={api_key}'
    )

    try:
        resp = httpx.post(
            url,
            json={'contents': [{'parts': [{'text': prompt}]}]},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get('candidates', [])
        if not candidates:
            raise GeminiError('No candidates returned from Gemini')

        text = candidates[0].get('content', {}).get('parts', [{}])[0].get('text', '')
        return text.strip()
    except httpx.HTTPError as e:
        raise GeminiError(f'Gemini API error: {e}') from e


def get_recommendations(title: str, artist: str, count: int = 10) -> list:
    cache_key = f'gemini_rec:{title}:{artist}:{count}'
    cached = cache.get(cache_key)
    if cached:
        return cached

    prompt = (
        f'Based on the song "{title}" by {artist}, suggest {count} other songs '
        f'with similar mood and genre. '
        f'Return ONLY a raw JSON array, each object with keys "title" and "artist". '
        f'No markdown, no code blocks, no extra text. '
        f'Example: [{{"title": "Song Name", "artist": "Artist Name"}}]'
    )

    try:
        text = _call_gemini(prompt)
    except GeminiError:
        return []

    text = text.strip()
    if text.startswith('```'):
        text = text.replace('```json', '').replace('```', '').strip()

    try:
        data = json.loads(text)
        if not isinstance(data, list):
            return []
        recommendations = [
            {'title': item.get('title', ''), 'artist': item.get('artist', '')}
            for item in data
            if item.get('title')
        ]
        cache.set(cache_key, recommendations, timeout=GEMINI_CACHE_TTL)
        return recommendations
    except (json.JSONDecodeError, KeyError):
        return []
