import uuid
import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.utils import timezone


class User(models.Model):
    """
    Model ánh xạ tới bảng 'users' do Supabase quản lý.
    managed=False vì Django không tạo/xóa bảng này — Supabase Auth tự xử lý.
    Không có trường password vì password được lưu riêng trong UserCredential
    (dành cho đăng ký nội bộ) hoặc do Supabase OAuth quản lý.
    """
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    avatar_url = models.TextField(blank=True, null=True)
    full_name = models.TextField(blank=True, null=True)
    email = models.TextField(blank=True, null=True, unique=True)
    username = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'users'

    @property
    def is_authenticated(self):
        # Luôn True vì User chỉ tồn tại khi đã xác thực qua session
        return True

    @property
    def is_anonymous(self):
        return False

    @property
    def is_active(self):
        return True

    def __str__(self):
        return self.email or str(self.id)

    def get_username(self):
        return self.email or str(self.id)


class UserCredential(models.Model):
    """
    Lưu password hash cho user đăng ký theo flow nội bộ (email + password).
    Tách khỏi User vì user đăng nhập qua Supabase OAuth sẽ không có credential này.
    Quan hệ OneToOne đảm bảo mỗi user chỉ có một bộ credential.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='credential')
    password_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_credentials'

    def set_password(self, raw_password):
        # Dùng Django's make_password để hash an toàn (PBKDF2 + salt)
        self.password_hash = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password_hash)


class UserSession(models.Model):
    """
    Session token-based authentication. Mỗi lần đăng nhập tạo một session mới.
    Token raw chỉ trả về cho client một lần, DB chỉ lưu hash của token để
    tránh lộ token nếu DB bị breach.
    Hỗ trợ multi-device: một user có thể có nhiều session hoạt động song song.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sessions')
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    device_id = models.CharField(max_length=255, blank=True)
    device_name = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_sessions'
        indexes = [
            models.Index(fields=['token_hash']),
            models.Index(fields=['user', 'revoked_at']),
        ]

    @staticmethod
    def hash_token(token):
        # SHA-256 đủ nhanh và an toàn cho lookup token trong DB
        return hashlib.sha256(token.encode('utf-8')).hexdigest()

    @classmethod
    def create_for_user(cls, user, request=None):
        """
        Tạo session mới cho user sau khi đăng nhập thành công.
        Trả về (token_raw, session): token_raw gửi về client, session lưu DB.
        TTL lấy từ settings.AUTH_SESSION_TTL_DAYS.
        """
        token = secrets.token_urlsafe(48)
        ttl = timedelta(days=settings.AUTH_SESSION_TTL_DAYS)
        session = cls.objects.create(
            user=user,
            token_hash=cls.hash_token(token),
            expires_at=timezone.now() + ttl,
            ip_address=cls._client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '') if request else '',
        )
        return token, session

    @staticmethod
    def _client_ip(request):
        """
        Ưu tiên X-Forwarded-For khi chạy sau reverse proxy (nginx, load balancer).
        Lấy IP đầu tiên trong chuỗi vì đó là IP client thực.
        """
        if not request:
            return None
        forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')

    @property
    def is_valid(self):
        # Session hợp lệ khi chưa bị revoke và chưa hết hạn
        return self.revoked_at is None and self.expires_at > timezone.now()

    def revoke(self):
        self.revoked_at = timezone.now()
        self.save(update_fields=['revoked_at'])
