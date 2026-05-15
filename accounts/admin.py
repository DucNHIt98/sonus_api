from django.contrib import admin

from .models import User, UserCredential, UserSession


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('email', 'username', 'full_name', 'created_at')
    search_fields = ('email', 'username', 'full_name')
    list_filter = ('created_at',)
    readonly_fields = ('id', 'created_at')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)


@admin.register(UserCredential)
class UserCredentialAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'updated_at')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'expires_at', 'revoked_at', 'last_used_at', 'device_name', 'ip_address')
    search_fields = ('user__email', 'user__username', 'device_name', 'ip_address')
    list_filter = ('expires_at', 'revoked_at', 'created_at')
    readonly_fields = ('id', 'token_hash', 'created_at', 'last_used_at')
    date_hierarchy = 'created_at'
