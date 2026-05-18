from django.utils import timezone
from rest_framework.permissions import BasePermission

from payments.models import Subscription

# Giới hạn tính năng cho tài khoản Free tier
FREE_DOWNLOAD_LIMIT = 20       # Tối đa 20 bài download
FREE_PLAYLIST_LIMIT = 5        # Tối đa 5 playlist
FREE_FAVORITE_LIMIT = 100      # Tối đa 100 bài yêu thích
FREE_HISTORY_DAYS = 7          # Lịch sử nghe chỉ xem được 7 ngày gần nhất
FREE_SEARCH_LIMIT = 10         # Mỗi lần tìm kiếm trả về tối đa 10 kết quả


def is_premium(user_id):
    """
    Kiểm tra user có đang là Premium không bằng cách tra bảng subscriptions.
    Chỉ tính subscription có status 'active' hoặc 'trialing' (dùng thử).
    Nếu current_period_end là None → subscription vĩnh viễn (không hết hạn).
    Lấy subscription mới nhất để tránh nhầm với subscription đã hết hạn trước đó.
    """
    sub = Subscription.objects.filter(
        user_id=user_id,
        status__in=['active', 'trialing'],
    ).order_by('-current_period_end').first()
    return sub is not None and (
        sub.current_period_end is None or sub.current_period_end > timezone.now()
    )


class IsPremiumUser(BasePermission):
    """
    DRF permission class: chặn API nếu user chưa là Premium.
    Dùng cho các endpoint chỉ dành cho Premium (vd: chart, export).
    """
    message = 'This feature requires a Premium subscription.'

    def has_permission(self, request, view):
        return request.user.is_authenticated and is_premium(str(request.user.id))
