from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import verify_supabase_jwt
from .models import User, UserSession
from .serializers import (
    LoginSerializer,
    RegisterSerializer,
    SupabaseExchangeSerializer,
    UserSerializer,
)


def auth_response(user, request, status_code=status.HTTP_200_OK):
    token, session = UserSession.create_for_user(user, request)
    return Response(
        {
            'user': UserSerializer(user).data,
            'token': token,
            'expires_at': session.expires_at,
        },
        status=status_code,
    )


class RegisterView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return auth_response(user, request, status.HTTP_201_CREATED)


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        return auth_response(serializer.validated_data['user'], request)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request.auth_session.revoke()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SupabaseExchangeView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SupabaseExchangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = verify_supabase_jwt(serializer.validated_data['token'])
        email = (payload.get('email') or '').lower()
        if not email:
            return Response({'detail': 'Supabase token missing email'}, status=status.HTTP_400_BAD_REQUEST)

        username = payload.get('user_metadata', {}).get('name') or email.split('@')[0]
        display_name = payload.get('user_metadata', {}).get('full_name') or username
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'username': username,
                'full_name': display_name,
                'avatar_url': payload.get('user_metadata', {}).get('avatar_url', ''),
            },
        )
        return auth_response(user, request)


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
