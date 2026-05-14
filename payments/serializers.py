from rest_framework import serializers


class CheckoutSessionSerializer(serializers.Serializer):
    success_url = serializers.URLField()
    cancel_url = serializers.URLField()


class CheckoutSessionResponseSerializer(serializers.Serializer):
    url = serializers.URLField()
    session_id = serializers.CharField()


class SubscriptionStatusSerializer(serializers.Serializer):
    is_premium = serializers.BooleanField()
    premium_until = serializers.DateTimeField(allow_null=True)
    status = serializers.CharField(allow_null=True)
    cancel_at_period_end = serializers.BooleanField()


class CancelSubscriptionResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    message = serializers.CharField()
