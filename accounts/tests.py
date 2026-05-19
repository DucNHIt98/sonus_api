from unittest.mock import patch

import pytest
from django.urls import reverse

from accounts.models import User, UserCredential, UserSession
from conftest import success_data, pagination, items


class TestRegisterView:
    def test_register_success(self, api_client, db):
        url = reverse('auth-register')
        data = {
            'email': 'newuser@example.com',
            'username': 'newuser',
            'password': 'Password123!',
        }
        response = api_client.post(url, data, format='json')
        assert response.status_code == 201
        result = success_data(response)
        assert result['user']['email'] == 'newuser@example.com'
        assert result['user']['username'] == 'newuser'
        assert 'token' in result
        assert User.objects.filter(email='newuser@example.com').exists()

    def test_register_duplicate_email(self, api_client, user):
        url = reverse('auth-register')
        data = {
            'email': 'test@example.com',
            'username': 'another',
            'password': 'Password123!',
        }
        response = api_client.post(url, data, format='json')
        assert response.status_code == 422


    def test_register_weak_password(self, api_client, db):
        url = reverse('auth-register')
        data = {
            'email': 'weak@example.com',
            'username': 'weakuser',
            'password': '123',
        }
        response = api_client.post(url, data, format='json')
        assert response.status_code == 422


    def test_register_with_display_name(self, api_client, db):
        url = reverse('auth-register')
        data = {
            'email': 'display@example.com',
            'username': 'displayuser',
            'password': 'Password123!',
            'display_name': 'Display Name',
        }
        response = api_client.post(url, data, format='json')
        assert response.status_code == 201
        user = User.objects.get(email='display@example.com')
        assert user.full_name == 'Display Name'


class TestLoginView:
    def test_login_success(self, api_client, user):
        UserCredential.objects.create(user=user)
        user.credential.set_password('CorrectPassword1!')
        user.credential.save()

        url = reverse('auth-login')
        response = api_client.post(url, {
            'email': 'test@example.com',
            'password': 'CorrectPassword1!',
        }, format='json')
        assert response.status_code == 200
        result = success_data(response)
        assert result['user']['email'] == 'test@example.com'
        assert 'token' in result

    def test_login_wrong_password(self, api_client, user):
        UserCredential.objects.create(user=user)
        user.credential.set_password('CorrectPassword1!')
        user.credential.save()

        url = reverse('auth-login')
        response = api_client.post(url, {
            'email': 'test@example.com',
            'password': 'WrongPassword',
        }, format='json')
        assert response.status_code == 422

    def test_login_nonexistent_email(self, api_client, db):
        url = reverse('auth-login')
        response = api_client.post(url, {
            'email': 'nobody@example.com',
            'password': 'SomePassword1!',
        }, format='json')
        assert response.status_code == 422


class TestLogoutView:
    def test_logout_success(self, auth_client):
        url = reverse('auth-logout')
        response = auth_client.post(url)
        assert response.status_code == 204

    def test_logout_without_auth(self, api_client):
        url = reverse('auth-logout')
        response = api_client.post(url)
        assert response.status_code == 403


class TestCurrentUserView:
    def test_get_current_user(self, auth_client):
        url = reverse('auth-me')
        response = auth_client.get(url)
        assert response.status_code == 200
        result = success_data(response)
        assert result['email'] == 'test@example.com'
        assert result['username'] == 'testuser'
        assert 'is_premium' in result
        assert 'stats' in result

    def test_get_current_user_unauthorized(self, api_client):
        url = reverse('auth-me')
        response = api_client.get(url)
        assert response.status_code == 403

    def test_update_display_name(self, auth_client):
        url = reverse('auth-me')
        response = auth_client.patch(url, {'display_name': 'Updated Name'}, format='json')
        assert response.status_code == 200
        result = success_data(response)
        assert result['display_name'] == 'Updated Name'


class TestAvatarUploadView:
    def test_upload_avatar_no_file(self, auth_client):
        url = reverse('auth-avatar')
        response = auth_client.post(url, format='multipart')
        assert response.status_code == 400

    def test_upload_avatar_unauthorized(self, api_client):
        url = reverse('auth-avatar')
        response = api_client.post(url, format='multipart')
        assert response.status_code == 403


class TestSupabaseExchangeView:
    @patch('accounts.views.verify_supabase_jwt')
    def test_google_exchange_success(self, mock_verify, api_client, db):
        mock_verify.return_value = {
            'email': 'google@example.com',
            'user_metadata': {
                'name': 'Google User',
                'full_name': 'Google Full Name',
                'avatar_url': 'https://example.com/avatar.jpg',
            },
        }
        url = reverse('auth-google')
        response = api_client.post(url, {'token': 'valid_supabase_token'}, format='json')
        assert response.status_code == 200
        result = success_data(response)
        assert result['user']['email'] == 'google@example.com'
        assert 'token' in result
        assert User.objects.filter(email='google@example.com').exists()

    def test_google_exchange_no_token(self, api_client):
        url = reverse('auth-google')
        response = api_client.post(url, {}, format='json')
        assert response.status_code == 422
