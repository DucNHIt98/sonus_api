from rest_framework import serializers

from .models import Lyric, Song, PlayHistory, LikedSong


class SongSerializer(serializers.ModelSerializer):
    """Serializer cơ bản cho bài hát, dùng trong các list view và nested serializers."""
    class Meta:
        model = Song
        fields = [
            'id', 'title', 'subtitle', 'image_url', 'audio_url',
            'album_name', 'source', 'genre', 'region', 'duration',
        ]


class PlayHistorySerializer(serializers.ModelSerializer):
    """
    Lịch sử nghe nhạc: nested SongSerializer để trả về đầy đủ thông tin bài hát.
    read_only=True vì song chỉ được ghi qua RecordPlayView, không qua serializer này.
    """
    song = SongSerializer(read_only=True)

    class Meta:
        model = PlayHistory
        fields = ['song', 'count', 'last_played']


class RecordPlaySerializer(serializers.Serializer):
    """
    Validate dữ liệu khi ghi nhận lượt nghe.
    progress_percent: client gửi % đã nghe để server biết có tính là 1 lượt không.
    Chỉ tính lượt nghe khi nghe ít nhất 50% bài (tránh skip nhanh bị tính).
    title, subtitle, image_url: gửi kèm để upsert vào bảng songs nếu chưa có.
    """
    song_id = serializers.CharField(required=True)
    progress_percent = serializers.FloatField(required=False, default=100, min_value=0, max_value=100)
    title = serializers.CharField(required=False, allow_blank=True)
    subtitle = serializers.CharField(required=False, allow_blank=True)
    image_url = serializers.CharField(required=False, allow_blank=True)
    duration = serializers.IntegerField(required=False, allow_null=True)

    def validate_progress_percent(self, value):
        if value < 50:
            raise serializers.ValidationError('Progress must be at least 50% to record a play')
        return value


class LikedSongSerializer(serializers.ModelSerializer):
    """
    Danh sách bài hát yêu thích.
    created_at là alias của trường liked_at trong DB (source='liked_at') —
    tên cột trong DB là liked_at nhưng API trả về là created_at để nhất quán với
    các list API khác (playlists, downloads đều dùng created_at).
    """
    song = SongSerializer(read_only=True)
    created_at = serializers.DateTimeField(source='liked_at', read_only=True)

    class Meta:
        model = LikedSong
        fields = ['song', 'created_at']


class ResolveAudioSerializer(serializers.Serializer):
    """
    Validate input cho endpoint resolve audio URL.
    Hỗ trợ nhiều cách identify bài hát:
    - video_id / youtube_id: YouTube video ID trực tiếp
    - title + artist: tìm kiếm YouTube để lấy ID
    - nct_url: lấy stream URL từ NCT
    - deezer_id: convert Deezer → YouTube
    """
    video_id = serializers.CharField(required=False)
    title = serializers.CharField(required=False)
    artist = serializers.CharField(required=False)
    deezer_id = serializers.CharField(required=False)
    youtube_id = serializers.CharField(required=False)
    nct_url = serializers.CharField(required=False)

    def validate(self, attrs):
        if not any(k in attrs for k in ('video_id', 'youtube_id', 'title', 'nct_url')):
            raise serializers.ValidationError('Provide video_id, youtube_id, title+artist, or nct_url')
        return attrs


class SearchSerializer(serializers.Serializer):
    """
    Validate query params cho endpoint tìm kiếm.
    sources: danh sách nguồn tìm kiếm cách nhau bởi dấu phẩy, vd: 'youtube,jamendo,nct'.
    """
    q = serializers.CharField(required=True)
    limit = serializers.IntegerField(default=10, min_value=1, max_value=50)
    sources = serializers.CharField(required=False, default='youtube,jamendo,nct')


class DownloadSongSerializer(serializers.Serializer):
    """
    Validate dữ liệu khi user đánh dấu download bài hát.
    Nhận metadata bài hát để upsert vào bảng songs nếu chưa tồn tại,
    đảm bảo bài hát luôn có record trong DB trước khi ghi download.
    """
    song_id = serializers.CharField(required=True)
    title = serializers.CharField(required=False, allow_blank=True, default='')
    subtitle = serializers.CharField(required=False, allow_blank=True, default='')
    image_url = serializers.CharField(required=False, allow_blank=True, default='')
    audio_url = serializers.CharField(required=False, allow_blank=True, default='')
    duration = serializers.IntegerField(required=False, allow_null=True, default=None)
    source = serializers.CharField(required=False, allow_blank=True, default='')


class DownloadedSongSerializer(serializers.Serializer):
    """Danh sách bài hát đã download, kèm thời gian download."""
    downloaded_at = serializers.DateTimeField()
    song = SongSerializer(read_only=True)


class LyricSerializer(serializers.ModelSerializer):
    """Lời bài hát: trả về cả plain text và synced (LRC format với timestamp)."""
    class Meta:
        model = Lyric
        fields = ['song_id', 'plain', 'synced', 'source', 'updated_at']
