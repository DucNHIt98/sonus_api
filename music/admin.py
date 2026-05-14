from django.contrib import admin

from .models import LikedSong, PlayHistory, Song

admin.site.register(Song)
admin.site.register(PlayHistory)
admin.site.register(LikedSong)
