import base64
import logging

from rest_framework import status as http_status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from django.core.cache import cache

logger = logging.getLogger(__name__)

from core.responses import success, created, no_content, bad_request, unauthorized
from .authentication import verify_supabase_jwt
from .models import User, UserSession
from .serializers import (
    LoginSerializer,
    RegisterSerializer,
    SupabaseExchangeSerializer,
    UserSerializer,
)


def auth_response(user, request, status_code=http_status.HTTP_200_OK):
    """
    Tạo session mới và trả về response chuẩn sau khi xác thực thành công.
    Dùng chung cho Register, Login và Supabase OAuth exchange.
    Response gồm: thông tin user, token raw (gửi về client một lần), expires_at.
    """
    try:
        token, session = UserSession.create_for_user(user, request)
    except Exception:
        logger.exception('Failed to create session for user %s', user.id)
        from core.responses import server_error
        return server_error('Failed to create session')
    data = {
        'user': UserSerializer(user).data,
        'token': token,
        'expires_at': session.expires_at,
    }
    if status_code == http_status.HTTP_201_CREATED:
        return created(data)
    return success(data)


class RegisterView(APIView):
    """
    Đăng ký tài khoản mới bằng email + password.
    authentication_classes=[] để bypass JWT check (chưa có token khi đăng ký).
    Sau khi tạo user thành công sẽ tự động tạo session và trả về token.
    """
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return auth_response(user, request, http_status.HTTP_201_CREATED)


class LoginView(APIView):
    """
    Đăng nhập bằng email + password nội bộ.
    authentication_classes=[] vì chưa có token khi đăng nhập.
    LoginSerializer.validate() trả về user object trong validated_data['user'].
    """
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        return auth_response(serializer.validated_data['user'], request)


class LogoutView(APIView):
    """
    Đăng xuất: revoke session trong DB và xóa cache để token không dùng được nữa.
    auth_session_cache_key được gắn vào request bởi DatabaseTokenAuthentication.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request.auth_session.revoke()
        cache_key = getattr(request, 'auth_session_cache_key', None)
        if cache_key:
            cache.delete(cache_key)
        return no_content()


class SupabaseExchangeView(APIView):
    """
    Exchange Supabase JWT lấy session nội bộ của Sonus API.
    Flow:
      1. Client đăng nhập qua Supabase (Google OAuth, ...) → nhận Supabase JWT
      2. Gửi JWT này lên endpoint này
      3. Server xác minh JWT, lấy email và metadata từ payload
      4. get_or_create User trong DB nội bộ, tạo session và trả về token

    Dùng get_or_create để tự động tạo tài khoản lần đầu đăng nhập qua OAuth.
    """
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SupabaseExchangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = verify_supabase_jwt(serializer.validated_data['token'])
        email = (payload.get('email') or '').lower()
        if not email:
            return bad_request('Supabase token missing email')

        # Lấy tên từ user_metadata nếu có, fallback về phần trước @ của email
        username = payload.get('user_metadata', {}).get('name') or email.split('@')[0]
        display_name = payload.get('user_metadata', {}).get('full_name') or username
        user, created_user = User.objects.get_or_create(
            email=email,
            defaults={
                'username': username,
                'full_name': display_name,
                'avatar_url': payload.get('user_metadata', {}).get('avatar_url', ''),
            },
        )
        return auth_response(user, request)


class CurrentUserView(APIView):
    """
    GET /me: Lấy thông tin user đang đăng nhập, kèm stats (số bài nghe, yêu thích, playlist).
    PATCH /me: Cập nhật display_name, avatar_url (partial update).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # include_stats=True để UserSerializer tính và trả về stats block
        return success(UserSerializer(request.user, context={'include_stats': True}).data)

    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return success(serializer.data)


class AvatarUploadView(APIView):
    """
    Upload avatar: nhận file ảnh, encode sang base64 data URL và lưu vào DB.
    Lưu dưới dạng data URL thay vì file storage để đơn giản hóa hạ tầng
    (không cần S3 hay CDN riêng).
    Giới hạn: 5MB, chỉ chấp nhận JPEG, PNG, WebP.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        avatar = request.FILES.get('avatar')
        if not avatar:
            return bad_request('No avatar file provided')

        if avatar.size > 5 * 1024 * 1024:
            return bad_request('File too large (max 5MB)')

        valid_types = ['image/jpeg', 'image/png', 'image/webp']
        if avatar.content_type not in valid_types:
            return bad_request('Invalid file type (JPEG, PNG, WebP only)')

        encoded = base64.b64encode(avatar.read()).decode('utf-8')
        # Tạo data URL chuẩn để frontend có thể dùng trực tiếp trong <img src="">
        data_url = f'data:{avatar.content_type};base64,{encoded}'

        user = request.user
        user.avatar_url = data_url
        user.save(update_fields=['avatar_url'])

        return success({'avatar_url': data_url})
