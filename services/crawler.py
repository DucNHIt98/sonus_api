import logging
from typing import Optional

from django.db import IntegrityError

from services.youtube import search_youtube, YouTubeError
from services.jamendo import search as jamendo_search, JamendoError
from services.nct import search as nct_search

from music.models import Song

logger = logging.getLogger(__name__)


def _save_songs(results: list, source: str) -> dict:
    saved = 0
    exists = 0
    errors = 0
    for r in results:
        song_id = r.get('id')
        if not song_id:
            errors += 1
            continue
        _, created = Song.objects.get_or_create(
            id=song_id,
            defaults={
                'title': (r.get('title') or '')[:500],
                'subtitle': (r.get('subtitle') or '')[:500],
                'image_url': (r.get('image_url') or '')[:500],
                'audio_url': (r.get('audio_url') or '')[:500],
                'duration': r.get('duration'),
                'source': r.get('source') or source,
            },
        )
        if created:
            saved += 1
        else:
            exists += 1
    return {'saved': saved, 'exists': exists, 'errors': errors}


def crawl_youtube(query: str, limit: int = 10) -> dict:
    try:
        results = search_youtube(query, limit)
        if not results:
            return {'saved': 0, 'exists': 0, 'errors': 0, 'source': 'youtube', 'query': query}
        return {**_save_songs(results, 'youtube'), 'source': 'youtube', 'query': query}
    except YouTubeError as e:
        logger.error('YouTube crawl failed: %s', e)
        return {'saved': 0, 'exists': 0, 'errors': 1, 'source': 'youtube', 'query': query, 'error': str(e)}


def crawl_jamendo(query: str, limit: int = 10) -> dict:
    try:
        results = jamendo_search(query, limit)
        if not results:
            return {'saved': 0, 'exists': 0, 'errors': 0, 'source': 'jamendo', 'query': query}
        return {**_save_songs(results, 'jamendo'), 'source': 'jamendo', 'query': query}
    except JamendoError as e:
        logger.error('Jamendo crawl failed: %s', e)
        return {'saved': 0, 'exists': 0, 'errors': 1, 'source': 'jamendo', 'query': query, 'error': str(e)}


def crawl_nct(query: str, limit: int = 10) -> dict:
    try:
        results = nct_search(query, limit)
        if not results:
            return {'saved': 0, 'exists': 0, 'errors': 0, 'source': 'nct', 'query': query}
        return {**_save_songs(results, 'nct'), 'source': 'nct', 'query': query}
    except Exception as e:
        logger.error('NCT crawl failed: %s', e)
        return {'saved': 0, 'exists': 0, 'errors': 1, 'source': 'nct', 'query': query, 'error': str(e)}


def crawl_queries(queries: list[dict]) -> list[dict]:
    results = []
    for q in queries:
        source = q.get('source', 'youtube')
        query = q['query']
        limit = q.get('limit', 10)
        if source == 'youtube':
            results.append(crawl_youtube(query, limit))
        elif source == 'jamendo':
            results.append(crawl_jamendo(query, limit))
        elif source == 'nct':
            results.append(crawl_nct(query, limit))
    return results
