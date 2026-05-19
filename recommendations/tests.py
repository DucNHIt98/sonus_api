from unittest.mock import patch

import pytest
from django.urls import reverse
from conftest import success_data


class TestRecommendView:
    @patch('recommendations.views.cache.get')
    @patch('recommendations.views.gemini_recommend')
    @patch('recommendations.views.search_youtube_best')
    def test_recommend_by_song_id(self, mock_yt, mock_gemini, mock_cache, auth_client, song):
        mock_cache.return_value = None
        mock_gemini.return_value = [
            {'title': 'Xylophone Melody', 'artist': 'Virtuoso'},
            {'title': 'Zephyr Breeze', 'artist': 'Wanderer'},
        ]
        mock_yt.side_effect = [
            {
                'id': 'yt_rec_1',
                'title': 'Xylophone Melody',
                'subtitle': 'Virtuoso',
                'image_url': 'https://example.com/rec.jpg',
                'duration': 200,
            },
            {
                'id': 'yt_rec_2',
                'title': 'Zephyr Breeze',
                'subtitle': 'Wanderer',
                'image_url': 'https://example.com/rec2.jpg',
                'duration': 180,
            },
        ]

        url = reverse('recommendations')
        response = auth_client.get(url, {'song_id': 'test_song_1'})
        assert response.status_code == 200
        result = success_data(response)
        assert len(result['recommendations']) >= 1

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
        assert success_data(response)['recommendations'][0]['id'] == 'cached_1'

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
        assert len(success_data(response)['recommendations']) == 1

    def test_recommend_unauthorized(self, api_client):
        url = reverse('recommendations')
        response = api_client.get(url, {'song_id': 'test'})
        assert response.status_code == 403
