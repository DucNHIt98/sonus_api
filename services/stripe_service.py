from datetime import datetime, timezone

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone as django_timezone

import stripe
from stripe._error import StripeError, SignatureVerificationError

from payments.models import Subscription


SUBSCRIPTION_STATUS_CACHE_TTL = 60


def _subscription_status_cache_key(user_id: str) -> str:
    return f'subscription-status:{user_id}'


def clear_subscription_status_cache(user_id: str):
    if user_id:
        cache.delete(_subscription_status_cache_key(user_id))


class StripeNotConfigured(Exception):
    pass


def _get_stripe():
    if not settings.STRIPE_SECRET_KEY:
        raise StripeNotConfigured('Stripe secret key not configured')
    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe


def create_checkout_session(user_id: str, success_url: str, cancel_url: str) -> dict:
    s = _get_stripe()

    price_id = settings.STRIPE_PREMIUM_PRICE_ID
    if not price_id:
        raise StripeNotConfigured('STRIPE_PREMIUM_PRICE_ID not configured')

    session = s.checkout.Session.create(
        mode='subscription',
        line_items=[{'price': price_id, 'quantity': 1}],
        client_reference_id=user_id,
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={'user_id': user_id},
    )
    return {'url': session.url, 'session_id': session.id}


def handle_webhook(payload: bytes, sig_header: str) -> dict:
    s = _get_stripe()
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET
    if not endpoint_secret:
        raise StripeNotConfigured('STRIPE_WEBHOOK_SECRET not configured')

    try:
        event = s.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except ValueError:
        return {'status': 'error', 'message': 'Invalid payload'}
    except SignatureVerificationError:
        return {'status': 'error', 'message': 'Invalid signature'}

    event_type = event.get('type')
    data = event.get('data', {}).get('object', {})

    handler = _EVENT_HANDLERS.get(event_type)
    if handler:
        handler(data)

    return {'status': 'success', 'event_type': event_type}


def _handle_checkout_completed(data: dict):
    user_id = data.get('metadata', {}).get('user_id') or data.get('client_reference_id')
    subscription_id = data.get('subscription')
    customer_id = data.get('customer')
    if not user_id or not subscription_id:
        return
    _upsert_subscription(
        user_id=user_id,
        stripe_subscription_id=subscription_id,
        stripe_customer_id=customer_id,
    )


def _handle_subscription_active(data: dict):
    sub_id = data.get('id')
    customer_id = data.get('customer')
    period_start = datetime.fromtimestamp(data.get('current_period_start', 0), tz=timezone.utc)
    period_end = datetime.fromtimestamp(data.get('current_period_end', 0), tz=timezone.utc)
    cancel_at_period_end = data.get('cancel_at_period_end', False)
    metadata = data.get('metadata', {})
    user_id = metadata.get('user_id') or _get_user_id_by_stripe_customer(customer_id)
    if not user_id:
        user_id = _get_user_id_by_subscription_id(sub_id)
    if not user_id:
        return
    _upsert_subscription(
        user_id=user_id,
        stripe_subscription_id=sub_id,
        stripe_customer_id=customer_id,
        status='active',
        period_start=period_start,
        period_end=period_end,
        cancel_at_period_end=cancel_at_period_end,
    )


def _handle_subscription_updated(data: dict):
    _handle_subscription_active(data)


def _handle_subscription_deleted(data: dict):
    sub_id = data.get('id')
    sub = Subscription.objects.filter(stripe_subscription_id=sub_id).first()
    if not sub:
        return
    Subscription.objects.filter(pk=sub.pk).update(
        status='canceled', updated_at=django_timezone.now(),
    )
    clear_subscription_status_cache(str(sub.user_id))


def _handle_invoice_payment_failed(data: dict):
    subscription_id = data.get('subscription')
    if not subscription_id:
        return
    sub = Subscription.objects.filter(stripe_subscription_id=subscription_id).first()
    if not sub:
        return
    Subscription.objects.filter(pk=sub.pk).update(
        status='past_due', updated_at=django_timezone.now(),
    )
    clear_subscription_status_cache(str(sub.user_id))


_EVENT_HANDLERS = {
    'checkout.session.completed': _handle_checkout_completed,
    'customer.subscription.updated': _handle_subscription_updated,
    'customer.subscription.deleted': _handle_subscription_deleted,
    'invoice.payment_succeeded': _handle_subscription_active,
    'invoice.payment_failed': _handle_invoice_payment_failed,
}


def cancel_subscription(user_id: str) -> dict:
    s = _get_stripe()

    sub = Subscription.objects.filter(user_id=user_id, status='active').first()
    if not sub:
        return {'status': 'error', 'message': 'No active subscription found'}

    try:
        s.Subscription.modify(sub.stripe_subscription_id, cancel_at_period_end=True)
    except StripeError as e:
        return {'status': 'error', 'message': str(e)}

    Subscription.objects.filter(stripe_subscription_id=sub.stripe_subscription_id).update(
        cancel_at_period_end=True, updated_at=django_timezone.now(),
    )
    clear_subscription_status_cache(user_id)

    return {'status': 'success', 'message': 'Subscription will cancel at period end'}


def get_subscription_status(user_id: str) -> dict:
    cache_key = _subscription_status_cache_key(user_id)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    sub = Subscription.objects.filter(
        user_id=user_id,
        status__in=['active', 'past_due', 'trialing'],
    ).order_by('-current_period_end').first()

    if not sub:
        result = {
            'is_premium': False,
            'premium_until': None,
            'status': None,
            'cancel_at_period_end': False,
        }
        cache.set(cache_key, result, timeout=SUBSCRIPTION_STATUS_CACHE_TTL)
        return result

    now = django_timezone.now()
    is_active = sub.status in ('active', 'trialing') and (
        sub.current_period_end is None or sub.current_period_end > now
    )

    result = {
        'is_premium': is_active,
        'premium_until': sub.current_period_end.isoformat() if sub.current_period_end else None,
        'status': sub.status,
        'cancel_at_period_end': sub.cancel_at_period_end,
    }
    cache.set(cache_key, result, timeout=SUBSCRIPTION_STATUS_CACHE_TTL)
    return result


def _upsert_subscription(
    user_id: str,
    stripe_subscription_id: str,
    stripe_customer_id: str = None,
    status: str = 'active',
    period_start=None,
    period_end=None,
    cancel_at_period_end: bool = False,
):
    sub, _ = Subscription.objects.update_or_create(
        stripe_subscription_id=stripe_subscription_id,
        defaults={
            'user_id': user_id,
            'stripe_customer_id': stripe_customer_id,
            'status': status,
            'current_period_start': period_start,
            'current_period_end': period_end,
            'cancel_at_period_end': cancel_at_period_end,
        },
    )
    clear_subscription_status_cache(str(sub.user_id))


def _get_user_id_by_stripe_customer(customer_id: str) -> str:
    sub = Subscription.objects.filter(stripe_customer_id=customer_id).first()
    return str(sub.user_id) if sub else None


def _get_user_id_by_subscription_id(sub_id: str) -> str:
    sub = Subscription.objects.filter(stripe_subscription_id=sub_id).first()
    return str(sub.user_id) if sub else None
