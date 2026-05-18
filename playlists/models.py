import uuid

from django.conf import settings
from django.db import models


class Playlist(models.Model):
    """
    Playlist do người dùng tạo ra. managed=False vì bảng 'playlists'
    được tạo bên ngoài Django (Supabase migration).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column='user_id',
    )
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
    """
    Bảng trung gian nối Playlist ↔ Song, lưu thêm trường position để
    duy trì thứ tự bài hát trong playlist (người dùng có thể reorder).
    created_at map tới cột 'added_at' trong DB (db_column='added_at').
    managed=False vì bảng tồn tại sẵn trong Supabase.
    """
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
    # Trong DB cột tên là 'added_at', Django alias thành created_at
    created_at = models.DateTimeField(db_column='added_at')

    class Meta:
        managed = False
        db_table = 'playlist_songs'
