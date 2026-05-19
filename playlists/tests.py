import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from playlists.models import Playlist, PlaylistSong
from music.models import Song

from conftest import success_data, pagination, items


_data = success_data
_pagination = pagination
_items = items


class TestPlaylistListView:
    def test_list_playlists(self, auth_client, playlist):
        url = reverse('playlists-list')
        response = auth_client.get(url)
        assert response.status_code == 200
        assert _pagination(response)['total'] == 1
        assert len(_items(response)) == 1
        assert _items(response)[0]['title'] == 'Test Playlist'

    def test_list_empty(self, auth_client):
        url = reverse('playlists-list')
        response = auth_client.get(url)
        assert response.status_code == 200
        assert _pagination(response)['total'] == 0

    def test_list_other_user_isolated(self, auth_client, user):
        other = Playlist.objects.create(
            user=user, title='Other', created_at=timezone.now(),
        )
        url = reverse('playlists-list')
        response = auth_client.get(url)
        assert _pagination(response)['total'] == 1  # only the one from auth_client's user

    def test_create_playlist(self, auth_client):
        url = reverse('playlists-list')
        response = auth_client.post(url, {
            'title': 'New Playlist',
            'description': 'A new one',
        }, format='json')
        assert response.status_code == 201
        result = _data(response)
        assert result['title'] == 'New Playlist'
        assert Playlist.objects.filter(title='New Playlist').exists()

    def test_create_playlist_limit(self, auth_client, user):
        from core.permissions import FREE_PLAYLIST_LIMIT
        for i in range(FREE_PLAYLIST_LIMIT):
            Playlist.objects.create(user=user, title=f'Playlist {i}', created_at=timezone.now())

        url = reverse('playlists-list')
        response = auth_client.post(url, {'title': 'Over Limit'}, format='json')
        assert response.status_code == 403
        assert 'limit' in response.json()['message'].lower()

    def test_create_playlist_premium_unlimited(self, auth_premium_client, user):
        from core.permissions import FREE_PLAYLIST_LIMIT
        for i in range(FREE_PLAYLIST_LIMIT):
            Playlist.objects.create(user=user, title=f'Playlist {i}', created_at=timezone.now())

        url = reverse('playlists-list')
        response = auth_premium_client.post(url, {'title': 'Premium Playlist'}, format='json')
        assert response.status_code == 201

    def test_create_playlist_unauthorized(self, api_client):
        url = reverse('playlists-list')
        response = api_client.post(url, {'title': 'Test'}, format='json')
        assert response.status_code == 403


class TestPlaylistDetailView:
    def test_get_detail(self, auth_client, playlist, song):
        PlaylistSong.objects.create(
            playlist=playlist, song=song,
            position=0, created_at=timezone.now(),
        )
        url = reverse('playlists-detail', args=[str(playlist.id)])
        response = auth_client.get(url)
        assert response.status_code == 200
        result = _data(response)
        assert result['title'] == 'Test Playlist'
        assert result['song_count'] == 1
        assert len(result['songs']) == 1

    def test_get_detail_not_found(self, auth_client):
        url = reverse('playlists-detail', args=['00000000-0000-0000-0000-000000000000'])
        response = auth_client.get(url)
        assert response.status_code == 404

    def test_get_detail_other_user(self, auth_client, db):
        other_user = User.objects.create(email='other@example.com', username='other')
        p = Playlist.objects.create(
            user=other_user, title='Other', created_at=timezone.now(),
        )
        url = reverse('playlists-detail', args=[str(p.id)])
        response = auth_client.get(url)
        assert response.status_code == 404

    def test_update_playlist(self, auth_client, playlist):
        url = reverse('playlists-detail', args=[str(playlist.id)])
        response = auth_client.patch(url, {'title': 'Updated Title'}, format='json')
        assert response.status_code == 200
        playlist.refresh_from_db()
        assert playlist.title == 'Updated Title'

    def test_update_playlist_no_fields(self, auth_client, playlist):
        url = reverse('playlists-detail', args=[str(playlist.id)])
        response = auth_client.patch(url, {}, format='json')
        assert response.status_code == 400
        assert response.json()['message'] == 'No fields to update'

    def test_delete_playlist(self, auth_client, playlist):
        url = reverse('playlists-detail', args=[str(playlist.id)])
        response = auth_client.delete(url)
        assert response.status_code == 204
        assert not Playlist.objects.filter(id=playlist.id).exists()

    def test_delete_not_found(self, auth_client):
        url = reverse('playlists-detail', args=['00000000-0000-0000-0000-000000000000'])
        response = auth_client.delete(url)
        assert response.status_code == 404


class TestPlaylistSongManageView:
    def test_add_song(self, auth_client, playlist, song):
        url = reverse('playlists-add-song', args=[str(playlist.id)])
        response = auth_client.post(url, {'song_id': 'test_song_1'}, format='json')
        assert response.status_code == 201
        assert PlaylistSong.objects.filter(playlist=playlist, song_id='test_song_1').exists()

    def test_add_duplicate_song(self, auth_client, playlist, song):
        PlaylistSong.objects.create(
            playlist=playlist, song=song,
            position=0, created_at=timezone.now(),
        )
        url = reverse('playlists-add-song', args=[str(playlist.id)])
        response = auth_client.post(url, {'song_id': 'test_song_1'}, format='json')
        assert response.status_code == 200
        assert response.json()['message'] == 'Song already in playlist'

    def test_add_song_nonexistent_playlist(self, auth_client, song):
        url = reverse('playlists-add-song', args=['00000000-0000-0000-0000-000000000000'])
        response = auth_client.post(url, {'song_id': 'test_song_1'}, format='json')
        assert response.status_code == 404

    def test_add_song_auto_positions(self, auth_client, playlist, song):
        PlaylistSong.objects.create(
            playlist=playlist, song=song,
            position=0, created_at=timezone.now(),
        )
        another = Song.objects.create(id='second_song', title='Second')
        url = reverse('playlists-add-song', args=[str(playlist.id)])
        response = auth_client.post(url, {'song_id': 'second_song'}, format='json')
        assert response.status_code == 201
        assert _data(response)['position'] == 1

    def test_remove_song(self, auth_client, playlist, song):
        PlaylistSong.objects.create(
            playlist=playlist, song=song,
            position=0, created_at=timezone.now(),
        )
        url = reverse('playlists-remove-song', args=[str(playlist.id), 'test_song_1'])
        response = auth_client.delete(url)
        assert response.status_code == 200
        assert not PlaylistSong.objects.filter(playlist=playlist, song_id='test_song_1').exists()

    def test_remove_nonexistent_song(self, auth_client, playlist):
        url = reverse('playlists-remove-song', args=[str(playlist.id), 'nosuch'])
        response = auth_client.delete(url)
        assert response.status_code == 404


class TestPlaylistReorderView:
    def test_reorder_songs(self, auth_client, playlist, song, another_song):
        PlaylistSong.objects.create(
            playlist=playlist, song=song,
            position=0, created_at=timezone.now(),
        )
        PlaylistSong.objects.create(
            playlist=playlist, song=another_song,
            position=1, created_at=timezone.now(),
        )
        url = reverse('playlists-reorder', args=[str(playlist.id)])
        response = auth_client.patch(url, {
            'song_ids': ['test_song_2', 'test_song_1'],
        }, format='json')
        assert response.status_code == 200
        positions = PlaylistSong.objects.filter(playlist=playlist).order_by('song_id')
        pos_map = {p.song_id: p.position for p in positions}
        assert pos_map['test_song_2'] == 0
        assert pos_map['test_song_1'] == 1

    def test_reorder_invalid(self, auth_client, playlist):
        url = reverse('playlists-reorder', args=[str(playlist.id)])
        response = auth_client.patch(url, {'song_ids': ['single']}, format='json')
        assert response.status_code == 400

    def test_reorder_not_found(self, auth_client):
        url = reverse('playlists-reorder', args=['00000000-0000-0000-0000-000000000000'])
        response = auth_client.patch(url, {'song_ids': ['a', 'b']}, format='json')
        assert response.status_code == 404
