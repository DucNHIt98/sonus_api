from django.urls import path

from .views import AvatarUploadView, CurrentUserView, LoginView, LogoutView, RegisterView, SupabaseExchangeView

urlpatterns = [
    path('auth/register/', RegisterView.as_view(), name='auth-register'),
    path('auth/login/', LoginView.as_view(), name='auth-login'),
    path('auth/logout/', LogoutView.as_view(), name='auth-logout'),
    path('auth/google/', SupabaseExchangeView.as_view(), name='auth-google'),
    path('auth/me/', CurrentUserView.as_view(), name='auth-me'),
    path('auth/me/avatar/', AvatarUploadView.as_view(), name='auth-avatar'),
]
