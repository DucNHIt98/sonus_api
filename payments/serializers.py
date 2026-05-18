from urllib.parse import urlparse

from rest_framework import serializers


class CheckoutSessionSerializer(serializers.Serializer):
    """
    Validate URL callback trước khi tạo Stripe Checkout Session.
    Cho phép scheme 'sonus://' để hỗ trợ deep link về mobile app
    sau khi thanh toán xong trên trình duyệt.
    """
    success_url = serializers.CharField()
    cancel_url = serializers.CharField()

    def validate_success_url(self, value):
        return self._validate_redirect_url(value)

    def validate_cancel_url(self, value):
        return self._validate_redirect_url(value)

    def _validate_redirect_url(self, value):
        """
        Chỉ cho phép http, https và sonus (deep link app).
        Phải có netloc (host) để tránh open redirect về path tùy ý.
        """
        parsed = urlparse(value)
        if parsed.scheme not in {'http', 'https', 'sonus'}:
            raise serializers.ValidationError('Unsupported redirect URL scheme')
        if not parsed.netloc:
            raise serializers.ValidationError('Redirect URL must include a host')
        return value


class CheckoutSessionResponseSerializer(serializers.Serializer):
    """Response khi tạo Stripe Checkout Session thành công."""
    url = serializers.URLField()
    session_id = serializers.CharField()


class SubscriptionStatusSerializer(serializers.Serializer):
    """Trạng thái subscription hiện tại của user, lấy từ Stripe."""
    is_premium = serializers.BooleanField()
    premium_until = serializers.DateTimeField(allow_null=True)
    status = serializers.CharField(allow_null=True)
    cancel_at_period_end = serializers.BooleanField()


class CancelSubscriptionResponseSerializer(serializers.Serializer):
    """Response khi user yêu cầu hủy subscription."""
    status = serializers.CharField()
    message = serializers.CharField()
