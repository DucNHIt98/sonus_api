import uuid

from django.db import models


class Playlist(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    image_url = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'playlists'

    def __str__(self):
        return self.title or str(self.id)


class PlaylistSong(models.Model):
    playlist = models.ForeignKey(
        Playlist,
        on_delete=models.CASCADE,
        db_column='playlist_id',
    )
    song = models.ForeignKey(
        'music.Song',
        on_delete=models.CASCADE,
        db_column='song_id',
    )
    position = models.IntegerField(default=0)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'playlist_songs'
