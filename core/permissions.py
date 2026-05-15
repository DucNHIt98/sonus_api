from django.utils import timezone
from rest_framework.permissions import BasePermission

from payments.models import Subscription

FREE_DOWNLOAD_LIMIT = 20
FREE_PLAYLIST_LIMIT = 5
FREE_FAVORITE_LIMIT = 100
FREE_HISTORY_DAYS = 7
FREE_SEARCH_LIMIT = 10


def is_premium(user_id):
    sub = Subscription.objects.filter(
        user_id=user_id,
        status__in=['active', 'trialing'],
    ).order_by('-current_period_end').first()
    return sub is not None and (
        sub.current_period_end is None or sub.current_period_end > timezone.now()
    )


class IsPremiumUser(BasePermission):
    message = 'This feature requires a Premium subscription.'

    def has_permission(self, request, view):
        return request.user.is_authenticated and is_premium(str(request.user.id))
