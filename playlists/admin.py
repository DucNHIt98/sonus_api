from django.contrib import admin

from .models import Playlist, PlaylistSong


class PlaylistSongInline(admin.TabularInline):
    model = PlaylistSong
    extra = 0
    readonly_fields = ('created_at',)
    raw_id_fields = ('song',)


@admin.register(Playlist)
class PlaylistAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'song_count', 'created_at')
    search_fields = ('title', 'description', 'user__email', 'user__username')
    list_filter = ('created_at',)
    readonly_fields = ('id', 'created_at')
    inlines = [PlaylistSongInline]

    def song_count(self, obj):
        return obj.playlistsong_set.count()
    song_count.short_description = 'Songs'


@admin.register(PlaylistSong)
class PlaylistSongAdmin(admin.ModelAdmin):
    list_display = ('playlist', 'song', 'position', 'created_at')
    search_fields = ('playlist__title', 'song__title')
    list_filter = ('created_at',)
    readonly_fields = ('created_at',)
