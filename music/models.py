from django.conf import settings
from django.db import models


class Song(models.Model):
    id = models.CharField(primary_key=True, max_length=500)
    title = models.TextField(blank=True, null=True)
    subtitle = models.TextField(blank=True, null=True)
    image_url = models.TextField(blank=True, null=True)
    audio_url = models.TextField(blank=True, null=True)
    album_name = models.TextField(blank=True, null=True)
    source = models.TextField(blank=True, null=True)
    genre = models.TextField(blank=True, null=True)
    region = models.TextField(blank=True, null=True)
    duration = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'songs'

    def __str__(self):
        return self.title or str(self.id)


class PlayHistory(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column='user_id',
    )
    song = models.ForeignKey(
        Song,
        on_delete=models.CASCADE,
        db_column='song_id',
    )
    count = models.IntegerField(default=1)
    last_played = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'play_history'
        unique_together = [['user', 'song']]


class LikedSong(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column='user_id',
    )
    song = models.ForeignKey(
        Song,
        on_delete=models.CASCADE,
        db_column='song_id',
    )
    liked_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'liked_songs'
        unique_together = [['user', 'song']]


class DownloadedSong(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column='user_id',
    )
    song = models.ForeignKey(
        Song,
        on_delete=models.CASCADE,
        db_column='song_id',
    )
    downloaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'downloaded_songs'
        unique_together = [['user', 'song']]

    def __str__(self):
        return f'{self.user_id} downloaded {self.song_id}'


class Lyric(models.Model):
    song = models.OneToOneField(
        Song,
        on_delete=models.CASCADE,
        primary_key=True,
        db_column='song_id',
    )
    plain = models.TextField(blank=True, null=True)
    synced = models.TextField(blank=True, null=True)
    source = models.CharField(max_length=50, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'song_lyrics'

    def __str__(self):
        return f'Lyrics for {self.song_id}'
