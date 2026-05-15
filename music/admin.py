from django.contrib import admin

from .models import DownloadedSong, LikedSong, Lyric, PlayHistory, Song


@admin.register(Song)
class SongAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'subtitle', 'source', 'genre', 'region', 'duration', 'created_at')
    search_fields = ('title', 'subtitle', 'album_name', 'id')
    list_filter = ('source', 'genre', 'region')
    readonly_fields = ('id', 'created_at')
    list_per_page = 50


@admin.register(PlayHistory)
class PlayHistoryAdmin(admin.ModelAdmin):
    list_display = ('user', 'song', 'count', 'last_played')
    search_fields = ('user__email', 'user__username', 'song__title')
    list_filter = ('last_played',)
    readonly_fields = ('last_played',)


@admin.register(LikedSong)
class LikedSongAdmin(admin.ModelAdmin):
    list_display = ('user', 'song', 'liked_at')
    search_fields = ('user__email', 'user__username', 'song__title')
    list_filter = ('liked_at',)
    readonly_fields = ('liked_at',)


@admin.register(DownloadedSong)
class DownloadedSongAdmin(admin.ModelAdmin):
    list_display = ('user', 'song', 'downloaded_at')
    search_fields = ('user__email', 'user__username', 'song__title')
    list_filter = ('downloaded_at',)
    readonly_fields = ('downloaded_at',)


@admin.register(Lyric)
class LyricAdmin(admin.ModelAdmin):
    list_display = ('song', 'source', 'has_plain', 'has_synced', 'updated_at')
    search_fields = ('song__title', 'song__id')
    readonly_fields = ('updated_at',)

    def has_plain(self, obj):
        return bool(obj.plain)
    has_plain.short_description = 'Plain'
    has_plain.boolean = True

    def has_synced(self, obj):
        return bool(obj.synced)
    has_synced.short_description = 'Synced'
    has_synced.boolean = True
