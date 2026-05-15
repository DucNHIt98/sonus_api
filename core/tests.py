import pytest
from django.urls import reverse


class TestHealthCheck:
    def test_health_check_returns_ok(self, api_client):
        url = reverse('health-check')
        response = api_client.get(url)
        assert response.status_code == 200
        assert response.json() == {'status': 'ok'}

    def test_health_check_no_auth_required(self, api_client):
        url = reverse('health-check')
        response = api_client.get(url)
        assert response.status_code == 200
