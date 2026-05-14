from django.urls import path

from . import views

urlpatterns = [
    path('payments/create-checkout-session/', views.create_checkout, name='create-checkout'),
    path('payments/webhook/', views.stripe_webhook, name='stripe-webhook'),
    path('payments/subscription/', views.subscription_status, name='subscription-status'),
    path('payments/subscription/cancel/', views.cancel_subscription_view, name='cancel-subscription'),
]
