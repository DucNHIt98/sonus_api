import json
import logging

from django.conf import settings
from django.views.decorators.csrf import csrf_exempt

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

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
    serializer = CheckoutSessionSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        result = create_checkout_session(
            user_id=str(request.user.id),
            success_url=serializer.validated_data['success_url'],
            cancel_url=serializer.validated_data['cancel_url'],
        )
        return Response(result)
    except StripeNotConfigured as e:
        return Response({'error': str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except Exception as e:
        logger.exception('Checkout session creation failed')
        return Response({'error': 'Failed to create checkout session'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
@authentication_classes([])
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')

    try:
        result = handle_webhook(payload, sig_header)
        return Response(result)
    except StripeNotConfigured as e:
        return Response({'error': str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except Exception as e:
        logger.exception('Webhook handling failed')
        return Response({'error': 'Webhook error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def subscription_status(request):
    result = get_subscription_status(user_id=str(request.user.id))
    serializer = SubscriptionStatusSerializer(result)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancel_subscription_view(request):
    try:
        result = cancel_subscription(user_id=str(request.user.id))
        return Response(result)
    except StripeNotConfigured as e:
        return Response({'error': str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except Exception as e:
        logger.exception('Cancel subscription failed')
        return Response({'error': 'Failed to cancel subscription'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
