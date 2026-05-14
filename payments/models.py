import uuid

from django.db import models

from accounts.models import User


class Subscription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_column='user_id')
    stripe_subscription_id = models.TextField(unique=True, null=True, blank=True)
    stripe_customer_id = models.TextField(null=True, blank=True)
    status = models.TextField(default='incomplete')
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'subscriptions'

    def __str__(self):
        return f'Subscription({self.user_id}, {self.status})'
