from datetime import datetime, timezone

from django.conf import settings
from django.db import connection
from django.utils import timezone

import stripe
from stripe._error import StripeError, SignatureVerificationError


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
    with connection.cursor() as cursor:
        cursor.execute(
            'UPDATE subscriptions SET status = %s, updated_at = NOW() WHERE stripe_subscription_id = %s',
            ['canceled', sub_id],
        )


def _handle_invoice_payment_failed(data: dict):
    subscription_id = data.get('subscription')
    if not subscription_id:
        return
    with connection.cursor() as cursor:
        cursor.execute(
            'UPDATE subscriptions SET status = %s, updated_at = NOW() WHERE stripe_subscription_id = %s',
            ['past_due', subscription_id],
        )


_EVENT_HANDLERS = {
    'checkout.session.completed': _handle_checkout_completed,
    'customer.subscription.updated': _handle_subscription_updated,
    'customer.subscription.deleted': _handle_subscription_deleted,
    'invoice.payment_succeeded': _handle_subscription_active,
    'invoice.payment_failed': _handle_invoice_payment_failed,
}


def cancel_subscription(user_id: str) -> dict:
    s = _get_stripe()

    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT stripe_subscription_id FROM subscriptions WHERE user_id = %s AND status = %s',
            [user_id, 'active'],
        )
        row = cursor.fetchone()

    if not row:
        return {'status': 'error', 'message': 'No active subscription found'}

    sub_id = row[0]
    try:
        s.Subscription.modify(sub_id, cancel_at_period_end=True)
    except StripeError as e:
        return {'status': 'error', 'message': str(e)}

    with connection.cursor() as cursor:
        cursor.execute(
            'UPDATE subscriptions SET cancel_at_period_end = TRUE, updated_at = NOW() WHERE stripe_subscription_id = %s',
            [sub_id],
        )

    return {'status': 'success', 'message': 'Subscription will cancel at period end'}


def get_subscription_status(user_id: str) -> dict:
    with connection.cursor() as cursor:
        cursor.execute(
            '''
            SELECT status, current_period_end, cancel_at_period_end, stripe_subscription_id
            FROM subscriptions
            WHERE user_id = %s AND status IN ('active', 'past_due', 'trialing')
            ORDER BY current_period_end DESC NULLS LAST
            LIMIT 1
            ''',
            [user_id],
        )
        row = cursor.fetchone()

    if not row:
        return {
            'is_premium': False,
            'premium_until': None,
            'status': None,
            'cancel_at_period_end': False,
        }

    status, period_end, cancel_at_period_end, _ = row

    now = timezone.now()
    is_active = status in ('active', 'trialing') and (period_end is None or period_end > now)

    return {
        'is_premium': is_active,
        'premium_until': period_end.isoformat() if period_end else None,
        'status': status,
        'cancel_at_period_end': cancel_at_period_end,
    }


def _upsert_subscription(
    user_id: str,
    stripe_subscription_id: str,
    stripe_customer_id: str = None,
    status: str = 'active',
    period_start=None,
    period_end=None,
    cancel_at_period_end: bool = False,
):
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT id FROM subscriptions WHERE stripe_subscription_id = %s',
            [stripe_subscription_id],
        )
        existing = cursor.fetchone()

        if existing:
            cursor.execute(
                '''
                UPDATE subscriptions
                SET status = %s, current_period_start = %s, current_period_end = %s,
                    cancel_at_period_end = %s, updated_at = NOW()
                WHERE stripe_subscription_id = %s
                ''',
                [status, period_start, period_end, cancel_at_period_end, stripe_subscription_id],
            )
        else:
            cursor.execute(
                '''
                INSERT INTO subscriptions (user_id, stripe_subscription_id, stripe_customer_id,
                    status, current_period_start, current_period_end, cancel_at_period_end)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''',
                [user_id, stripe_subscription_id, stripe_customer_id,
                 status, period_start, period_end, cancel_at_period_end],
            )


def _get_user_id_by_stripe_customer(customer_id: str) -> str:
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT user_id FROM subscriptions WHERE stripe_customer_id = %s LIMIT 1',
            [customer_id],
        )
        row = cursor.fetchone()
    return str(row[0]) if row else None


def _get_user_id_by_subscription_id(sub_id: str) -> str:
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT user_id FROM subscriptions WHERE stripe_subscription_id = %s LIMIT 1',
            [sub_id],
        )
        row = cursor.fetchone()
    return str(row[0]) if row else None
