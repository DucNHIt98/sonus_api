from django.conf import settings
from django.db import models


class Song(models.Model):
    """
    Bài hát trong hệ thống. managed=False vì bảng 'songs' tồn tại sẵn trong DB
    và được ghi bởi nhiều service (crawler, search cache, NCT, Jamendo).
    id là YouTube video ID, Jamendo track ID, NCT ID, ... (không phải UUID).
    source cho biết bài hát đến từ đâu: 'youtube', 'jamendo', 'nct', 'deezer_preview'.
    audio_url có thể null nếu chỉ lưu metadata (YouTube cần resolve lại).
    """
    id = models.CharField(primary_key=True, max_length=500)
    title = models.TextField(blank=True, null=True)
    subtitle = models.TextField(blank=True, null=True)   # Tên nghệ sĩ / artist
    image_url = models.TextField(blank=True, null=True)
    audio_url = models.TextField(blank=True, null=True)
    album_name = models.TextField(blank=True, null=True)
    source = models.TextField(blank=True, null=True)
    genre = models.TextField(blank=True, null=True)
    region = models.TextField(blank=True, null=True)
    duration = models.IntegerField(null=True, blank=True)  # Giây
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'songs'

    def __str__(self):
        return self.title or str(self.id)


class PlayHistory(models.Model):
    """
    Lịch sử nghe nhạc của user. Mỗi cặp (user, song) là duy nhất —
    thay vì tạo nhiều record, cập nhật count và last_played.
    Dùng PostgreSQL UPSERT trong RecordPlayView để đảm bảo atomicity.
    """
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
    count = models.IntegerField(default=1)       # Tổng số lần nghe
    last_played = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'play_history'
        unique_together = [['user', 'song']]


class LikedSong(models.Model):
    """
    Bài hát yêu thích của user.
    liked_at (không phải created_at) là tên cột trong DB.
    LikedSongSerializer alias trường này thành created_at trong API response.
    """
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
    """
    Theo dõi bài hát đã download (offline) của user.
    Dùng để enforce giới hạn FREE_DOWNLOAD_LIMIT cho tài khoản Free.
    unique_together đảm bảo mỗi bài chỉ tính một lần trong quota.
    """
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
    """
    Lời bài hát, OneToOne với Song (một bài chỉ có một bộ lời).
    plain: lời text thường.
    synced: lời có timestamp (định dạng LRC) để hiển thị karaoke.
    source: nguồn lấy lời (vd: 'lrclib', 'genius').
    Nếu chưa có lời trong DB, LyricsView sẽ gọi fetch_and_store_lyrics() để lấy từ API ngoài.
    """
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
