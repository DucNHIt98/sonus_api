import jwt
from django.conf import settings
from django.core.cache import cache
from jwt import InvalidTokenError
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from rest_framework import serializers

from .models import UserSession


# Cache session trong RAM để tránh DB query mỗi request.
# TTL 120s: đủ ngắn để phát hiện revoke sớm, đủ dài để giảm tải DB.
AUTH_SESSION_CACHE_TTL = 120


class DatabaseTokenAuthentication(BaseAuthentication):
    """
    Custom authentication dùng Bearer token được lưu trong DB (bảng user_sessions).
    Flow xác thực:
      1. Đọc token từ header Authorization: Bearer <token>
      2. Hash token → tìm trong Redis cache trước
      3. Nếu cache miss → query DB, sau đó cache lại session
      4. Kiểm tra session.is_valid và user.is_active
    """
    keyword = 'Bearer'

    def authenticate(self, request):
        auth = get_authorization_header(request).split()
        if not auth:
            return None
        if len(auth) != 2 or auth[0].decode().lower() != self.keyword.lower():
            raise AuthenticationFailed('Invalid authorization header')

        token = auth[1].decode()
        token_hash = UserSession.hash_token(token)
        cache_key = f'auth-session:{token_hash}'
        session = cache.get(cache_key)

        # Nếu cache hit và session còn hợp lệ thì bỏ qua DB query
        if (
            session
            and hasattr(session, 'is_valid')
            and hasattr(session, 'user')
            and session.is_valid
            and session.user.is_active
        ):
            request.auth_session = session
            request.auth_session_cache_key = cache_key
            return session.user, session

        try:
            session = UserSession.objects.select_related('user').get(token_hash=token_hash)
        except UserSession.DoesNotExist as exc:
            raise AuthenticationFailed('Invalid or expired token') from exc

        if not session.is_valid or not session.user.is_active:
            raise AuthenticationFailed('Invalid or expired token')

        # Gắn session vào request để LogoutView có thể revoke và xóa cache
        request.auth_session = session
        request.auth_session_cache_key = cache_key
        cache.set(cache_key, session, timeout=AUTH_SESSION_CACHE_TTL)
        return session.user, session


def verify_supabase_jwt(token):
    """
    Xác minh JWT do Supabase cấp khi user đăng nhập qua OAuth (Google, GitHub, ...).
    Dùng HS256 + SUPABASE_JWT_SECRET từ settings.
    Supabase yêu cầu audience='authenticated' và issuer đúng project URL.
    Nếu hợp lệ, trả về payload chứa email, user_metadata (avatar, full_name, ...).
    """
    if not settings.SUPABASE_JWT_SECRET:
        raise serializers.ValidationError('Supabase JWT secret is not configured')

    issuer = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1"
    try:
        return jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=['HS256'],
            audience='authenticated',
            issuer=issuer,
        )
    except InvalidTokenError as exc:
        raise serializers.ValidationError('Invalid Supabase token') from exc
