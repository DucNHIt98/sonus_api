from datetime import timedelta
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone

from music.models import DownloadedSong, LikedSong, PlayHistory, Song


class TestResolveAudioView:
    @patch('music.views.extract_audio_url')
    def test_resolve_by_video_id(self, mock_extract, auth_client):
        mock_extract.return_value = {
            'audio_url': 'https://example.com/audio.mp3',
            'expires_at': '2026-06-01T00:00:00Z',
            'title': 'Test Song',
            'duration': 240,
        }
        url = reverse('music-resolve')
        response = auth_client.post(url, {'video_id': 'test_video_id'}, format='json')
        assert response.status_code == 200
        result = response.json()
        assert result['youtube_id'] == 'test_video_id'
        assert result['audio_url'] == 'https://example.com/audio.mp3'

    @patch('music.views.extract_audio_url')
    def test_resolve_by_youtube_id(self, mock_extract, auth_client):
        mock_extract.return_value = {
            'audio_url': 'https://example.com/audio.mp3',
            'expires_at': '2026-06-01T00:00:00Z',
            'title': 'Test Song',
            'duration': 240,
        }
        url = reverse('music-resolve')
        response = auth_client.post(url, {'youtube_id': 'test_video_id'}, format='json')
        assert response.status_code == 200
        assert response.json()['youtube_id'] == 'test_video_id'

    @patch('music.views.convert_deezer_to_youtube')
    @patch('music.views.extract_audio_url')
    def test_resolve_by_title(self, mock_extract, mock_convert, auth_client):
        mock_convert.return_value = {'id': 'yt_from_deezer'}
        mock_extract.return_value = {
            'audio_url': 'https://example.com/audio.mp3',
            'expires_at': '2026-06-01T00:00:00Z',
            'title': 'Resolved Title',
            'duration': 200,
        }
        url = reverse('music-resolve')
        response = auth_client.post(url, {'title': 'Some Song', 'artist': 'Some Artist'}, format='json')
        assert response.status_code == 200
        assert response.json()['youtube_id'] == 'yt_from_deezer'

    def test_resolve_no_params(self, auth_client):
        url = reverse('music-resolve')
        response = auth_client.post(url, {}, format='json')
        assert response.status_code == 400

    def test_resolve_unauthorized(self, api_client):
        url = reverse('music-resolve')
        response = api_client.post(url, {'video_id': 'abc'}, format='json')
        assert response.status_code == 403

    @patch('music.views.extract_audio_url')
    def test_resolve_youtube_error(self, mock_extract, auth_client):
        from services.youtube import YouTubeError
        mock_extract.side_effect = YouTubeError('YouTube API error')
        url = reverse('music-resolve')
        response = auth_client.post(url, {'video_id': 'bad_id'}, format='json')
        assert response.status_code == 502


class TestSearchView:
    @patch('music.views.search_youtube')
    @patch('music.views.jamendo_search')
    def test_search_all_sources(self, mock_jamendo, mock_youtube, auth_client):
        mock_youtube.return_value = [
            {'id': 'yt1', 'title': 'YT Song', 'subtitle': 'YT Artist'},
        ]
        mock_jamendo.return_value = [
            {'id': 'jam1', 'title': 'Jamendo Song', 'subtitle': 'Jamendo Artist'},
        ]
        url = reverse('music-search')
        response = auth_client.get(url, {'q': 'test', 'sources': 'youtube,jamendo'})
        assert response.status_code == 200
        result = response.json()
        assert result['total'] == 2
        assert len(result['results']) == 2
        assert result.get('truncated') is False

    def test_search_no_query(self, auth_client):
        url = reverse('music-search')
        response = auth_client.get(url)
        assert response.status_code == 400

    def test_search_unauthorized(self, api_client):
        url = reverse('music-search')
        response = api_client.get(url, {'q': 'test'})
        assert response.status_code == 403

    @patch('music.views.search_youtube')
    @patch('music.views.jamendo_search')
    def test_search_truncated_for_free(self, mock_jamendo, mock_youtube, auth_client):
        mock_youtube.return_value = [
            {'id': f'yt{i}', 'title': f'YT Song {i}', 'subtitle': 'YT Artist'}
            for i in range(8)
        ]
        mock_jamendo.return_value = [
            {'id': f'jam{i}', 'title': f'Jam Song {i}', 'subtitle': 'Jam Artist'}
            for i in range(8)
        ]
        url = reverse('music-search')
        response = auth_client.get(url, {'q': 'test', 'sources': 'youtube,jamendo'})
        assert response.status_code == 200
        result = response.json()
        assert result['total'] == 10  # FREE_SEARCH_LIMIT
        assert result['truncated'] is True

    @patch('music.views.search_youtube')
    def test_search_full_results_premium(self, mock_youtube, auth_premium_client):
        mock_youtube.return_value = [
            {'id': f'yt{i}', 'title': f'YT Song {i}', 'subtitle': 'YT Artist'}
            for i in range(15)
        ]
        url = reverse('music-search')
        response = auth_premium_client.get(url, {'q': 'test', 'sources': 'youtube'})
        assert response.status_code == 200
        result = response.json()
        assert result['total'] == 15
        assert result['truncated'] is False

    @patch('music.views.search_youtube')
    def test_search_partial_failure(self, mock_youtube, auth_client):
        from services.youtube import YouTubeError
        mock_youtube.side_effect = YouTubeError('YouTube down')
        url = reverse('music-search')
        response = auth_client.get(url, {'q': 'test', 'sources': 'youtube,jamendo'})
        assert response.status_code == 200
        assert response.json()['errors'] is not None


class TestAutocompleteView:
    @patch('music.views.get_autocomplete')
    def test_autocomplete(self, mock_ac, auth_client):
        mock_ac.return_value = ['Shape of You', 'Shallow']
        url = reverse('music-autocomplete')
        response = auth_client.get(url, {'q': 'sha'})
        assert response.status_code == 200
        assert response.json()['suggestions'] == ['Shape of You', 'Shallow']

    def test_autocomplete_short_query(self, auth_client):
        url = reverse('music-autocomplete')
        response = auth_client.get(url, {'q': 's'})
        assert response.status_code == 200
        assert response.json()['suggestions'] == []


class TestHomeFeedView:
    @patch('music.views.cache.get')
    @patch('music.views.nct_get_chart')
    @patch('music.views.jamendo_genre')
    @patch('music.views.jamendo_discovery')
    def test_home_feed_free_reduced(self, mock_discovery, mock_genre, mock_chart, mock_cache, auth_client):
        mock_cache.return_value = None
        mock_chart.return_value = [{'id': 'nct1', 'title': 'NCT Song'}]
        mock_genre.return_value = [{'id': 'jam1', 'title': 'Jamendo Song'}]
        mock_discovery.return_value = [{'id': 'disc1', 'title': 'Trending Song'}]

        url = reverse('music-feed')
        response = auth_client.get(url)
        assert response.status_code == 200
        result = response.json()
        assert 'trending' not in result
        assert 'charts' not in result
        assert 'genres' in result

    @patch('music.views.cache.get')
    @patch('music.views.nct_get_chart')
    @patch('music.views.jamendo_genre')
    @patch('music.views.jamendo_discovery')
    def test_home_feed_premium_full(self, mock_discovery, mock_genre, mock_chart, mock_cache, auth_premium_client):
        mock_cache.return_value = None
        mock_chart.return_value = [{'id': 'nct1', 'title': 'NCT Song'}]
        mock_genre.return_value = [{'id': 'jam1', 'title': 'Jamendo Song'}]
        mock_discovery.return_value = [{'id': 'disc1', 'title': 'Trending Song'}]

        url = reverse('music-feed')
        response = auth_premium_client.get(url)
        assert response.status_code == 200
        result = response.json()
        assert 'trending' in result
        assert 'charts' in result
        assert 'genres' in result

    @patch('music.views.cache.get')
    def test_home_feed_cached(self, mock_cache, auth_client):
        mock_cache.return_value = {'genres': {}}
        url = reverse('music-feed')
        with patch('music.views.nct_get_chart') as mock_chart:
            response = auth_client.get(url)
            assert response.status_code == 200
            mock_chart.assert_not_called()


class TestChartDetailView:
    @patch('music.views.nct_get_chart')
    def test_chart_detail_premium(self, mock_chart, auth_premium_client):
        mock_chart.return_value = [{'id': '1', 'title': 'Chart Song'}]
        url = reverse('music-charts')
        response = auth_premium_client.get(url, {'region': 'v-pop'})
        assert response.status_code == 200
        assert response.json()['region'] == 'v-pop'

    def test_chart_free_blocked(self, auth_client):
        url = reverse('music-charts')
        response = auth_client.get(url)
        assert response.status_code == 403

    @patch('music.views.nct_get_chart')
    def test_chart_premium_no_region(self, mock_chart, auth_premium_client):
        url = reverse('music-charts')
        response = auth_premium_client.get(url)
        assert response.status_code == 400


class TestGenreTrackListView:
    @patch('music.views.jamendo_genre')
    def test_genre_tracks_premium(self, mock_genre, auth_premium_client):
        mock_genre.return_value = [{'id': '1', 'title': 'Genre Song'}]
        url = reverse('music-genres')
        response = auth_premium_client.get(url, {'genre': 'rock'})
        assert response.status_code == 200

    def test_genre_free_blocked(self, auth_client):
        url = reverse('music-genres')
        response = auth_client.get(url)
        assert response.status_code == 403

    @patch('music.views.jamendo_genre')
    def test_genre_premium_no_param(self, mock_genre, auth_premium_client):
        url = reverse('music-genres')
        response = auth_premium_client.get(url)
        assert response.status_code == 400


class TestRecordPlayView:
    def test_record_play(self, auth_client, song):
        url = reverse('history-record')
        response = auth_client.post(url, {
            'song_id': 'test_song_1',
            'progress_percent': 51,
        }, format='json')
        assert response.status_code == 200
        assert PlayHistory.objects.filter(user=auth_client.user, song_id='test_song_1').exists()

    def test_record_play_creates_song(self, auth_client):
        url = reverse('history-record')
        response = auth_client.post(url, {
            'song_id': 'new_song',
            'progress_percent': 75,
            'title': 'New Song',
            'subtitle': 'New Artist',
        }, format='json')
        assert response.status_code == 200
        assert Song.objects.filter(id='new_song').exists()

    def test_record_play_below_threshold(self, auth_client):
        url = reverse('history-record')
        response = auth_client.post(url, {
            'song_id': 'test_song_1',
            'progress_percent': 30,
        }, format='json')
        assert response.status_code == 400

    def test_record_play_increments_count(self, auth_client, song):
        PlayHistory.objects.create(
            user=auth_client.user, song=song,
            count=1, last_played=timezone.now(),
        )
        url = reverse('history-record')
        response = auth_client.post(url, {
            'song_id': 'test_song_1',
            'progress_percent': 90,
        }, format='json')
        assert response.status_code == 200
        assert response.json()['count'] == 2


class TestPlayHistoryView:
    def test_get_history(self, auth_client, song):
        PlayHistory.objects.create(
            user=auth_client.user, song=song,
            count=3, last_played=timezone.now(),
        )
        url = reverse('history-list')
        response = auth_client.get(url)
        assert response.status_code == 200
        result = response.json()
        assert result['total'] == 1
        assert len(result['history']) == 1
        assert result['history'][0]['count'] == 3

    def test_get_history_empty(self, auth_client):
        url = reverse('history-list')
        response = auth_client.get(url)
        assert response.status_code == 200
        assert response.json()['total'] == 0

    def test_delete_single_entry(self, auth_client, song):
        PlayHistory.objects.create(
            user=auth_client.user, song=song,
            count=1, last_played=timezone.now(),
        )
        url = reverse('history-list')
        response = auth_client.delete(f'{url}?song_id=test_song_1')
        assert response.status_code == 200
        assert not PlayHistory.objects.filter(user=auth_client.user).exists()

    def test_delete_all_history(self, auth_client, song):
        PlayHistory.objects.create(
            user=auth_client.user, song=song,
            count=1, last_played=timezone.now(),
        )
        url = reverse('history-list')
        response = auth_client.delete(url)
        assert response.status_code == 200

    def test_delete_nonexistent(self, auth_client):
        url = reverse('history-list')
        response = auth_client.delete(f'{url}?song_id=nonexistent')
        assert response.status_code == 404


class TestTopPlayedView:
    def test_top_played(self, auth_client, song, another_song):
        PlayHistory.objects.create(
            user=auth_client.user, song=song,
            count=10, last_played=timezone.now(),
        )
        PlayHistory.objects.create(
            user=auth_client.user, song=another_song,
            count=5, last_played=timezone.now(),
        )
        url = reverse('history-top')
        response = auth_client.get(url)
        assert response.status_code == 200
        result = response.json()
        assert len(result['top']) == 2
        assert result['top'][0]['count'] == 10

    def test_top_played_empty(self, auth_client):
        url = reverse('history-top')
        response = auth_client.get(url)
        assert response.status_code == 200
        assert response.json()['top'] == []


class TestFavoriteToggleView:
    def test_add_favorite(self, auth_client, song):
        url = reverse('favorites-toggle', args=['test_song_1'])
        response = auth_client.post(url, {'liked': True}, format='json')
        assert response.status_code == 200
        assert response.json()['liked'] is True
        assert LikedSong.objects.filter(user=auth_client.user, song_id='test_song_1').exists()

    def test_remove_favorite(self, auth_client, song):
        LikedSong.objects.create(
            user=auth_client.user, song=song, liked_at=timezone.now(),
        )
        url = reverse('favorites-toggle', args=['test_song_1'])
        response = auth_client.post(url, {'liked': False}, format='json')
        assert response.status_code == 200
        assert response.json()['liked'] is False
        assert not LikedSong.objects.filter(user=auth_client.user, song_id='test_song_1').exists()


class TestFavoriteListView:
    def test_list_favorites(self, auth_client, song, another_song):
        LikedSong.objects.create(
            user=auth_client.user, song=song, liked_at=timezone.now(),
        )
        LikedSong.objects.create(
            user=auth_client.user, song=another_song, liked_at=timezone.now(),
        )
        url = reverse('favorites-list')
        response = auth_client.get(url)
        assert response.status_code == 200
        result = response.json()
        assert result['total'] == 2
        assert len(result['favorites']) == 2

    def test_list_favorites_empty(self, auth_client):
        url = reverse('favorites-list')
        response = auth_client.get(url)
        assert response.status_code == 200
        assert response.json()['total'] == 0

    def test_list_favorites_pagination(self, auth_client, song):
        LikedSong.objects.create(
            user=auth_client.user, song=song, liked_at=timezone.now(),
        )
        url = reverse('favorites-list')
        response = auth_client.get(url, {'offset': 0, 'limit': 1})
        assert response.status_code == 200
        assert len(response.json()['favorites']) == 1


class TestDownloadSongView:
    def test_download_song(self, auth_client, song):
        url = reverse('downloads-song', args=['test_song_1'])
        response = auth_client.post(url, {'title': 'Test Song'}, format='json')
        assert response.status_code == 201
        assert DownloadedSong.objects.filter(user=auth_client.user, song_id='test_song_1').exists()

    def test_download_twice_idempotent(self, auth_client, song):
        DownloadedSong.objects.create(user=auth_client.user, song=song)
        url = reverse('downloads-song', args=['test_song_1'])
        response = auth_client.post(url, format='json')
        assert response.status_code == 200
        assert response.json()['detail'] == 'Song already downloaded'

    def test_download_creates_song(self, auth_client):
        url = reverse('downloads-song', args=['new_download_song'])
        response = auth_client.post(url, {
            'title': 'New Download',
            'subtitle': 'Artist',
        }, format='json')
        assert response.status_code == 201
        assert Song.objects.filter(id='new_download_song').exists()

    def test_remove_download(self, auth_client, song):
        DownloadedSong.objects.create(user=auth_client.user, song=song)
        url = reverse('downloads-song', args=['test_song_1'])
        response = auth_client.delete(url)
        assert response.status_code == 200
        assert not DownloadedSong.objects.filter(user=auth_client.user, song_id='test_song_1').exists()

    def test_remove_nonexistent_download(self, auth_client):
        url = reverse('downloads-song', args=['nonexistent'])
        response = auth_client.delete(url)
        assert response.status_code == 404

    def test_download_limit_free_user(self, auth_client, song, another_song):
        from core.permissions import FREE_DOWNLOAD_LIMIT
        for i in range(FREE_DOWNLOAD_LIMIT):
            s = Song.objects.create(id=f'bulk_{i}', title=f'Bulk {i}')
            DownloadedSong.objects.create(user=auth_client.user, song=s)

        url = reverse('downloads-song', args=['test_song_1'])
        response = auth_client.post(url, format='json')
        assert response.status_code == 403
        assert 'limit' in response.json()['detail'].lower()

    def test_premium_user_unlimited(self, auth_premium_client, song):
        url = reverse('downloads-song', args=['test_song_1'])
        response = auth_premium_client.post(url, format='json')
        assert response.status_code == 201


class TestDownloadedSongsView:
    def test_list_downloads(self, auth_client, song, another_song):
        DownloadedSong.objects.create(user=auth_client.user, song=song)
        DownloadedSong.objects.create(user=auth_client.user, song=another_song)
        url = reverse('downloads-list')
        response = auth_client.get(url)
        assert response.status_code == 200
        result = response.json()
        assert result['total'] == 2
        assert len(result['downloads']) == 2

    def test_list_downloads_empty(self, auth_client):
        url = reverse('downloads-list')
        response = auth_client.get(url)
        assert response.status_code == 200
        assert response.json()['total'] == 0

    def test_list_downloads_song_details(self, auth_client, song):
        DownloadedSong.objects.create(user=auth_client.user, song=song)
        url = reverse('downloads-list')
        response = auth_client.get(url)
        song_data = response.json()['downloads'][0]['song']
        assert song_data['id'] == 'test_song_1'
        assert song_data['title'] == 'Test Song'


class TestDownloadQuotaView:
    def test_free_user_quota(self, auth_client):
        url = reverse('downloads-quota')
        response = auth_client.get(url)
        assert response.status_code == 200
        result = response.json()
        assert result['is_premium'] is False
        assert result['downloads_used'] == 0
        assert result['downloads_limit'] == 20

    def test_premium_user_quota(self, auth_premium_client):
        url = reverse('downloads-quota')
        response = auth_premium_client.get(url)
        assert response.status_code == 200
        result = response.json()
        assert result['is_premium'] is True
        assert result['downloads_limit'] is None

    def test_quota_reflects_count(self, auth_client, song):
        DownloadedSong.objects.create(user=auth_client.user, song=song)
        url = reverse('downloads-quota')
        response = auth_client.get(url)
        assert response.json()['downloads_used'] == 1


class TestPlayHistoryPremiumGate:
    def test_history_filtered_to_7_days_for_free(self, auth_client, song):
        old_date = timezone.now() - timedelta(days=10)
        PlayHistory.objects.create(
            user=auth_client.user, song=song,
            count=1, last_played=old_date,
        )
        url = reverse('history-list')
        response = auth_client.get(url)
        assert response.status_code == 200
        result = response.json()
        assert result['total'] == 0  # filtered out

    def test_history_shows_recent_for_free(self, auth_client, song):
        PlayHistory.objects.create(
            user=auth_client.user, song=song,
            count=1, last_played=timezone.now(),
        )
        url = reverse('history-list')
        response = auth_client.get(url)
        assert response.status_code == 200
        assert response.json()['total'] == 1

    def test_history_full_for_premium(self, auth_premium_client, song):
        old_date = timezone.now() - timedelta(days=10)
        PlayHistory.objects.create(
            user=auth_premium_client.user, song=song,
            count=1, last_played=old_date,
        )
        url = reverse('history-list')
        response = auth_premium_client.get(url)
        assert response.status_code == 200
        assert response.json()['total'] == 1


class TestTopPlayedPremiumGate:
    def test_top_played_filtered_to_7_days_for_free(self, auth_client, song):
        old_date = timezone.now() - timedelta(days=10)
        PlayHistory.objects.create(
            user=auth_client.user, song=song,
            count=10, last_played=old_date,
        )
        url = reverse('history-top')
        response = auth_client.get(url)
        assert response.status_code == 200
        assert len(response.json()['top']) == 0

    def test_top_played_premium_sees_all(self, auth_premium_client, song):
        old_date = timezone.now() - timedelta(days=10)
        PlayHistory.objects.create(
            user=auth_premium_client.user, song=song,
            count=10, last_played=old_date,
        )
        url = reverse('history-top')
        response = auth_premium_client.get(url)
        assert response.status_code == 200
        assert len(response.json()['top']) == 1


class TestFavoriteLimitGate:
    def test_favorite_limit_reached(self, auth_client):
        from core.permissions import FREE_FAVORITE_LIMIT
        for i in range(FREE_FAVORITE_LIMIT):
            s = Song.objects.create(id=f'fav_limit_{i}', title=f'Fav {i}')
            LikedSong.objects.create(user=auth_client.user, song=s, liked_at=timezone.now())

        url = reverse('favorites-toggle', args=['new_song'])
        response = auth_client.post(url, {'liked': True}, format='json')
        assert response.status_code == 403
        assert 'limit' in response.json()['detail'].lower()

    def test_favorite_limit_premium_unlimited(self, auth_premium_client):
        from core.permissions import FREE_FAVORITE_LIMIT
        for i in range(FREE_FAVORITE_LIMIT):
            s = Song.objects.create(id=f'fav_prem_{i}', title=f'Fav Prem {i}')
            LikedSong.objects.create(user=auth_premium_client.user, song=s, liked_at=timezone.now())

        Song.objects.create(id='new_prem_song', title='New Premium Song')
        url = reverse('favorites-toggle', args=['new_prem_song'])
        response = auth_premium_client.post(url, {'liked': True}, format='json')
        assert response.status_code == 200
        assert response.json()['liked'] is True


class TestHomeFeedPremiumGate:
    @patch('music.views.cache.get')
    @patch('music.views.nct_get_chart')
    @patch('music.views.jamendo_genre')
    @patch('music.views.jamendo_discovery')
    def test_feed_reduced_for_free(self, mock_discovery, mock_genre, mock_chart, mock_cache, auth_client):
        mock_cache.return_value = None
        mock_chart.return_value = [{'id': 'nct1', 'title': 'NCT'}]
        mock_genre.return_value = [{'id': 'jam1', 'title': 'Jamendo'}]
        mock_discovery.return_value = [{'id': 'disc1', 'title': 'Trending'}]

        url = reverse('music-feed')
        response = auth_client.get(url)
        assert response.status_code == 200
        result = response.json()
        assert 'trending' not in result
        assert 'charts' not in result
        assert 'genres' in result

    @patch('music.views.cache.get')
    @patch('music.views.nct_get_chart')
    @patch('music.views.jamendo_genre')
    @patch('music.views.jamendo_discovery')
    def test_feed_full_for_premium(self, mock_discovery, mock_genre, mock_chart, mock_cache, auth_premium_client):
        mock_cache.return_value = None
        mock_chart.return_value = [{'id': 'nct1', 'title': 'NCT'}]
        mock_genre.return_value = [{'id': 'jam1', 'title': 'Jamendo'}]
        mock_discovery.return_value = [{'id': 'disc1', 'title': 'Trending'}]

        url = reverse('music-feed')
        response = auth_premium_client.get(url)
        assert response.status_code == 200
        result = response.json()
        assert 'trending' in result
        assert 'charts' in result
        assert 'genres' in result


class TestChartDetailPremiumGate:
    def test_chart_premium_required(self, auth_client):
        url = reverse('music-charts')
        response = auth_client.get(url, {'region': 'v-pop'})
        assert response.status_code == 403

    @patch('music.views.nct_get_chart')
    def test_chart_premium_allowed(self, mock_chart, auth_premium_client):
        mock_chart.return_value = [{'id': '1', 'title': 'Chart Song'}]
        url = reverse('music-charts')
        response = auth_premium_client.get(url, {'region': 'v-pop'})
        assert response.status_code == 200


class TestGenreTrackPremiumGate:
    def test_genre_premium_required(self, auth_client):
        url = reverse('music-genres')
        response = auth_client.get(url, {'genre': 'rock'})
        assert response.status_code == 403

    @patch('music.views.jamendo_genre')
    def test_genre_premium_allowed(self, mock_genre, auth_premium_client):
        mock_genre.return_value = [{'id': '1', 'title': 'Genre Song'}]
        url = reverse('music-genres')
        response = auth_premium_client.get(url, {'genre': 'rock'})
        assert response.status_code == 200


class TestLyricsView:
    def test_lyrics_not_found(self, auth_client, song):
        url = reverse('song-lyrics', args=['test_song_1'])
        with patch('services.lyrics.fetch_and_store_lyrics', return_value=None):
            response = auth_client.get(url)
        assert response.status_code == 404
