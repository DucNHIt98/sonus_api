import jwt
from django.conf import settings
from django.core.cache import cache
from jwt import InvalidTokenError
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from rest_framework import serializers

from .models import UserSession


AUTH_SESSION_CACHE_TTL = 120


class DatabaseTokenAuthentication(BaseAuthentication):
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

        request.auth_session = session
        request.auth_session_cache_key = cache_key
        cache.set(cache_key, session, timeout=AUTH_SESSION_CACHE_TTL)
        return session.user, session


def verify_supabase_jwt(token):
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
