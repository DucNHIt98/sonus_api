from unittest.mock import patch

import pytest
from django.urls import reverse


class TestRecommendView:
    @patch('recommendations.views.cache.get')
    @patch('recommendations.views.gemini_recommend')
    @patch('recommendations.views.search_youtube_best')
    def test_recommend_by_song_id(self, mock_yt, mock_gemini, mock_cache, auth_client, song):
        mock_cache.return_value = None
        mock_gemini.return_value = [
            {'title': 'Rec 1', 'artist': 'Artist 1'},
            {'title': 'Rec 2', 'artist': 'Artist 2'},
        ]
        mock_yt.return_value = {
            'id': 'yt_rec_1',
            'title': 'Rec 1',
            'subtitle': 'Artist 1',
            'image_url': 'https://example.com/rec.jpg',
            'duration': 200,
        }

        url = reverse('recommendations')
        response = auth_client.get(url, {'song_id': 'test_song_1'})
        assert response.status_code == 200
        result = response.json()
        assert len(result['recommendations']) == 2

    def test_recommend_no_params(self, auth_client):
        url = reverse('recommendations')
        response = auth_client.get(url)
        assert response.status_code == 400

    @patch('recommendations.views.cache.get')
    @patch('recommendations.views.gemini_recommend')
    @patch('recommendations.views.search_youtube_best')
    def test_recommend_by_title(self, mock_yt, mock_gemini, mock_cache, auth_client):
        mock_cache.return_value = None
        mock_gemini.return_value = []
        url = reverse('recommendations')
        response = auth_client.get(url, {'title': 'Test', 'artist': 'Artist'})
        assert response.status_code == 200

    @patch('recommendations.views.cache.get')
    def test_recommend_cached(self, mock_cache, auth_client, song):
        mock_cache.return_value = {'recommendations': [{'id': 'cached_1'}]}
        url = reverse('recommendations')
        response = auth_client.get(url, {'song_id': 'test_song_1'})
        assert response.status_code == 200
        assert response.json()['recommendations'][0]['id'] == 'cached_1'

    @patch('recommendations.views.cache.get')
    @patch('recommendations.views.gemini_recommend')
    @patch('recommendations.views.get_related_videos')
    def test_recommend_fallback_to_related(self, mock_related, mock_gemini, mock_cache, auth_client, song):
        mock_cache.return_value = None
        mock_gemini.return_value = []
        mock_related.return_value = [{'id': 'rel_1', 'title': 'Related'}]
        url = reverse('recommendations')
        response = auth_client.get(url, {'song_id': 'test_song_1'})
        assert response.status_code == 200
        assert len(response.json()['recommendations']) == 1

    def test_recommend_unauthorized(self, api_client):
        url = reverse('recommendations')
        response = api_client.get(url, {'song_id': 'test'})
        assert response.status_code == 403
