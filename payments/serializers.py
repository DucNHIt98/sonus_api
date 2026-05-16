from urllib.parse import urlparse

from rest_framework import serializers


class CheckoutSessionSerializer(serializers.Serializer):
    success_url = serializers.CharField()
    cancel_url = serializers.CharField()

    def validate_success_url(self, value):
        return self._validate_redirect_url(value)

    def validate_cancel_url(self, value):
        return self._validate_redirect_url(value)

    def _validate_redirect_url(self, value):
        parsed = urlparse(value)
        if parsed.scheme not in {'http', 'https', 'sonus'}:
            raise serializers.ValidationError('Unsupported redirect URL scheme')
        if not parsed.netloc:
            raise serializers.ValidationError('Redirect URL must include a host')
        return value


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
