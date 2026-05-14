from django.contrib import admin

from .models import Playlist, PlaylistSong

admin.site.register(Playlist)
admin.site.register(PlaylistSong)
