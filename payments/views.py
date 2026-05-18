import logging

from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny, IsAuthenticated

from core.responses import success, bad_request, service_unavailable, server_error
from .serializers import CheckoutSessionSerializer, SubscriptionStatusSerializer
from services.stripe_service import (
    StripeNotConfigured,
    create_checkout_session,
    handle_webhook,
    cancel_subscription,
    get_subscription_status,
)

logger = logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_checkout(request):
    """
    Tạo Stripe Checkout Session để user thanh toán nâng cấp Premium.
    Stripe trả về URL redirect đến trang thanh toán của họ.
    success_url và cancel_url là nơi Stripe redirect sau khi thanh toán xong/hủy.
    """
    serializer = CheckoutSessionSerializer(data=request.data)
    if not serializer.is_valid():
        return bad_request('Validation failed', errors=serializer.errors)

    try:
        result = create_checkout_session(
            user_id=str(request.user.id),
            success_url=serializer.validated_data['success_url'],
            cancel_url=serializer.validated_data['cancel_url'],
        )
        return success(result)
    except StripeNotConfigured as e:
        return service_unavailable(str(e))
    except Exception:
        logger.exception('Checkout session creation failed')
        return server_error('Failed to create checkout session')


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
@authentication_classes([])
def stripe_webhook(request):
    """
    Nhận sự kiện webhook từ Stripe (payment succeeded, subscription canceled, ...).
    @csrf_exempt vì Stripe gọi từ server ngoài, không có CSRF token.
    AllowAny + authentication_classes=[] vì Stripe không gửi Bearer token —
    thay vào đó xác thực bằng chữ ký HMAC trong header 'Stripe-Signature'.
    handle_webhook() trong stripe_service xác minh chữ ký và cập nhật DB.
    """
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')

    try:
        result = handle_webhook(payload, sig_header)
        return success(result)
    except StripeNotConfigured as e:
        return service_unavailable(str(e))
    except Exception:
        logger.exception('Webhook handling failed')
        return server_error('Webhook error')


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def subscription_status(request):
    """
    Trả về trạng thái subscription hiện tại: is_premium, premium_until,
    Stripe status, và cancel_at_period_end (đã lên lịch hủy chưa).
    """
    result = get_subscription_status(user_id=str(request.user.id))
    return success(SubscriptionStatusSerializer(result).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancel_subscription_view(request):
    """
    Lên lịch hủy subscription: Stripe sẽ không gia hạn vào kỳ tiếp theo,
    nhưng user vẫn dùng được Premium đến hết current_period_end.
    Stripe gọi webhook 'customer.subscription.deleted' khi thực sự hết hạn.
    """
    try:
        result = cancel_subscription(user_id=str(request.user.id))
        return success(result)
    except StripeNotConfigured as e:
        return service_unavailable(str(e))
    except Exception:
        logger.exception('Cancel subscription failed')
        return server_error('Failed to cancel subscription')
