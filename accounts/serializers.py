from django.db import connection
from rest_framework import serializers

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
        from services.stripe_service import get_subscription_status
        try:
            result = get_subscription_status(str(obj.id))
            return result['is_premium']
        except Exception:
            return False

    def get_premium_until(self, obj):
        from services.stripe_service import get_subscription_status
        try:
            result = get_subscription_status(str(obj.id))
            return result['premium_until']
        except Exception:
            return None

    def get_stats(self, obj):
        user_id = str(obj.id)
        with connection.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM play_history WHERE user_id = %s', [user_id])
            listened = cursor.fetchone()[0]
            cursor.execute('SELECT COUNT(*) FROM liked_songs WHERE user_id = %s', [user_id])
            favorites = cursor.fetchone()[0]
            cursor.execute('SELECT COUNT(*) FROM playlists')
            playlists = cursor.fetchone()[0]
        return {
            'listened_count': listened,
            'favorites_count': favorites,
            'playlists_count': playlists,
        }


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
