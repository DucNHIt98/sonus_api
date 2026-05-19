from datetime import timedelta
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone

from payments.models import Subscription
from conftest import success_data


class TestCreateCheckoutView:
    @patch('payments.views.create_checkout_session')
    def test_create_checkout(self, mock_checkout, auth_client):
        mock_checkout.return_value = {
            'url': 'https://checkout.stripe.com/test',
            'session_id': 'cs_test_123',
        }
        url = reverse('create-checkout')
        response = auth_client.post(url, {
            'success_url': 'https://example.com/success',
            'cancel_url': 'https://example.com/cancel',
        }, format='json')
        assert response.status_code == 200
        assert 'url' in success_data(response)
        mock_checkout.assert_called_once()

    def test_create_checkout_unauthorized(self, api_client):
        url = reverse('create-checkout')
        response = api_client.post(url, {
            'success_url': 'https://example.com/success',
            'cancel_url': 'https://example.com/cancel',
        }, format='json')
        assert response.status_code == 403

    @patch('payments.views.create_checkout_session')
    def test_create_checkout_service_error(self, mock_checkout, auth_client):
        from services.stripe_service import StripeNotConfigured
        mock_checkout.side_effect = StripeNotConfigured('Stripe not configured')
        url = reverse('create-checkout')
        response = auth_client.post(url, {
            'success_url': 'https://example.com/success',
            'cancel_url': 'https://example.com/cancel',
        }, format='json')
        assert response.status_code == 503


class TestSubscriptionStatusView:
    def test_subscription_status_free(self, auth_client):
        url = reverse('subscription-status')
        response = auth_client.get(url)
        assert response.status_code == 200
        result = success_data(response)
        assert result['is_premium'] is False
        assert result['status'] is None

    def test_subscription_status_premium(self, auth_client, premium_subscription):
        url = reverse('subscription-status')
        response = auth_client.get(url)
        assert response.status_code == 200
        result = success_data(response)
        assert result['is_premium'] is True
        assert result['status'] == 'active'

    def test_subscription_status_expired(self, auth_client):
        Subscription.objects.create(
            user=auth_client.user,
            stripe_subscription_id='sub_expired',
            status='active',
            current_period_start=timezone.now() - timedelta(days=60),
            current_period_end=timezone.now() - timedelta(days=30),
        )
        url = reverse('subscription-status')
        response = auth_client.get(url)
        assert success_data(response)['is_premium'] is False


class TestCancelSubscriptionView:
    @patch('payments.views.cancel_subscription')
    def test_cancel_subscription(self, mock_cancel, auth_client, premium_subscription):
        mock_cancel.return_value = {'status': 'success', 'message': 'Subscription cancelled'}
        url = reverse('cancel-subscription')
        response = auth_client.post(url)
        assert response.status_code == 200

    @patch('payments.views.cancel_subscription')
    def test_cancel_no_subscription(self, mock_cancel, auth_client):
        mock_cancel.return_value = {'status': 'error', 'message': 'No active subscription found'}
        url = reverse('cancel-subscription')
        response = auth_client.post(url)
        assert response.status_code == 200
        assert success_data(response)['status'] == 'error'


class TestStripeWebhookView:
    @patch('payments.views.handle_webhook')
    def test_webhook_success(self, mock_handle, api_client):
        mock_handle.return_value = {'status': 'success', 'event_type': 'checkout.session.completed'}
        url = reverse('stripe-webhook')
        response = api_client.post(
            url,
            data='{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='test_sig',
        )
        assert response.status_code == 200
        assert success_data(response)['status'] == 'success'

    @patch('payments.views.handle_webhook')
    def test_webhook_service_error(self, mock_handle, api_client):
        from services.stripe_service import StripeNotConfigured
        mock_handle.side_effect = StripeNotConfigured('Stripe not configured')
        url = reverse('stripe-webhook')
        response = api_client.post(
            url,
            data='{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='test_sig',
        )
        assert response.status_code == 503
