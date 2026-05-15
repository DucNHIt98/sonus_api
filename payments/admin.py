from django.contrib import admin

from .models import Subscription


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'status', 'stripe_subscription_id', 'current_period_start', 'current_period_end', 'cancel_at_period_end', 'created_at')
    search_fields = ('user__email', 'user__username', 'stripe_subscription_id', 'stripe_customer_id')
    list_filter = ('status', 'cancel_at_period_end', 'created_at')
    readonly_fields = ('id', 'created_at', 'updated_at')
    date_hierarchy = 'created_at'
