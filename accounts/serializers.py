from rest_framework import serializers
from django.core.cache import cache

from .models import User, UserCredential


class UserSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(source='full_name', required=False, allow_blank=True)
    is_premium = serializers.SerializerMethodField()
    premium_until = serializers.SerializerMethodField()
    stats = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'username',
            'display_name',
            'avatar_url',
            'is_premium',
            'premium_until',
            'stats',
        ]
        read_only_fields = ['id', 'email', 'username', 'is_premium', 'premium_until', 'stats']

    def get_is_premium(self, obj):
        return self._subscription_status(obj).get('is_premium', False)

    def get_premium_until(self, obj):
        return self._subscription_status(obj).get('premium_until')

    def _subscription_status(self, obj):
        if 'subscription_status' in self.context:
            return self.context['subscription_status']
        from services.stripe_service import get_subscription_status
        try:
            return get_subscription_status(str(obj.id))
        except Exception:
            return {'is_premium': False, 'premium_until': None}

    def get_stats(self, obj):
        if not self.context.get('include_stats', False):
            return None
        cache_key = f'user-stats:{obj.id}'
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        from music.models import LikedSong, PlayHistory
        from playlists.models import Playlist

        stats = {
            'listened_count': PlayHistory.objects.filter(user=obj).count(),
            'favorites_count': LikedSong.objects.filter(user=obj).count(),
            'playlists_count': Playlist.objects.filter(user=obj).count(),
        }
        cache.set(cache_key, stats, timeout=60)
        return stats


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, min_length=8)
    display_name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate_email(self, value):
        email = value.lower()
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError('Email is already registered')
        return email

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError('Username is already taken')
        return value

    def create(self, validated_data):
        password = validated_data.pop('password')
        display_name = validated_data.pop('display_name', '') or validated_data['username']
        user = User.objects.create(
            email=validated_data['email'],
            username=validated_data['username'],
            full_name=display_name,
        )
        credential = UserCredential(user=user)
        credential.set_password(password)
        credential.save()
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = User.objects.filter(email=attrs['email'].lower()).first()
        if not user or not hasattr(user, 'credential'):
            raise serializers.ValidationError('Invalid email or password')
        if not user.credential.check_password(attrs['password']):
            raise serializers.ValidationError('Invalid email or password')
        attrs['user'] = user
        return attrs


class SupabaseExchangeSerializer(serializers.Serializer):
    token = serializers.CharField()
