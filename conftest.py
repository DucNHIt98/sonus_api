from datetime import timedelta

import pytest
from django.conf import settings
from django.db import connection
from django.utils import timezone


def success_data(response):
    return response.json()['data']

def pagination(response):
    return response.json()['data']['pagination']

def items(response):
    return response.json()['data']['items']

from accounts.models import User, UserSession
from music.models import DownloadedSong, LikedSong, Lyric, PlayHistory, Song
from payments.models import Subscription
from playlists.models import Playlist, PlaylistSong


_UNMANAGED_MODELS = [
    User,
    Song,
    PlayHistory,
    LikedSong,
    Lyric,
    Playlist,
    PlaylistSong,
    Subscription,
]


def _create_tables():
    with connection.schema_editor(collect_sql=False, atomic=False) as editor:
        for model in _UNMANAGED_MODELS:
            try:
                editor.create_model(model)
            except Exception:
                pass


@pytest.fixture(scope='session', autouse=True)
def django_db_setup(django_db_setup, django_db_blocker):
    with django_db_blocker.unblock():
        _create_tables()


@pytest.fixture
def user(db):
    return User.objects.create(
        email='test@example.com',
        username='testuser',
        full_name='Test User',
    )


@pytest.fixture
def user_session(user):
    token, session = UserSession.create_for_user(user)
    session.last_used_at = timezone.now()
    session.save(update_fields=['last_used_at'])
    return token, session


@pytest.fixture
def auth_headers(user_session):
    token, _ = user_session
    return {'HTTP_AUTHORIZATION': f'Bearer {token}'}


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient
    return APIClient()


@pytest.fixture
def auth_client(api_client, auth_headers, user):
    client = api_client
    client.credentials(**auth_headers)
    client.user = user
    return client


@pytest.fixture
def song(db):
    return Song.objects.create(
        id='test_song_1',
        title='Test Song',
        subtitle='Test Artist',
        image_url='https://example.com/image.jpg',
        audio_url='https://example.com/audio.mp3',
        duration=240,
        source='youtube',
    )


@pytest.fixture
def another_song(db):
    return Song.objects.create(
        id='test_song_2',
        title='Another Song',
        subtitle='Another Artist',
        image_url='https://example.com/image2.jpg',
        duration=200,
        source='youtube',
    )


@pytest.fixture
def playlist(user, db):
    return Playlist.objects.create(
        user=user,
        title='Test Playlist',
        description='A test playlist',
        created_at=timezone.now(),
    )


@pytest.fixture
def premium_subscription(user, db):
    return Subscription.objects.create(
        user=user,
        stripe_subscription_id='sub_premium',
        stripe_customer_id='cus_premium',
        status='active',
        current_period_start=timezone.now() - timedelta(days=10),
        current_period_end=timezone.now() + timedelta(days=20),
    )


@pytest.fixture
def auth_premium_client(api_client, user, premium_subscription, db):
    from rest_framework.test import APIClient
    token, _ = UserSession.create_for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    client.user = user
    return client
