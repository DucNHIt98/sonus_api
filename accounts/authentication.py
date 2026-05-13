import jwt
from django.conf import settings
from jwt import InvalidTokenError
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from rest_framework import serializers

from .models import UserSession


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
        try:
            session = UserSession.objects.select_related('user').get(token_hash=token_hash)
        except UserSession.DoesNotExist as exc:
            raise AuthenticationFailed('Invalid or expired token') from exc

        if not session.is_valid or not session.user.is_active:
            raise AuthenticationFailed('Invalid or expired token')

        request.auth_session = session
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
