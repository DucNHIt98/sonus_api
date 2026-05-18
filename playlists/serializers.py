from rest_framework import serializers

from .models import Playlist, PlaylistSong


class PlaylistSongSerializer(serializers.Serializer):
    """
    Serialize bài hát trong playlist. Dùng source='song.xxx' để flatten
    thông tin từ quan hệ PlaylistSong → Song thành một level.
    Thêm trường position để frontend biết thứ tự hiển thị.
    """
    id = serializers.CharField(source='song.id')
    title = serializers.CharField(source='song.title')
    subtitle = serializers.CharField(source='song.subtitle')
    image_url = serializers.CharField(source='song.image_url')
    audio_url = serializers.CharField(source='song.audio_url')
    duration = serializers.IntegerField(source='song.duration', allow_null=True)
    source = serializers.CharField(source='song.source')
    position = serializers.IntegerField()


class PlaylistListSerializer(serializers.ModelSerializer):
    """
    Serialize playlist trong danh sách. song_count là IntegerField (không phải
    SerializerMethodField) vì giá trị đến từ annotation .annotate(song_count=Count(...))
    trong queryset — đọc trực tiếp qua getattr, không query DB thêm lần nào.
    """
    song_count = serializers.IntegerField()

    class Meta:
        model = Playlist
        fields = ['id', 'title', 'description', 'image_url', 'song_count', 'created_at']


class PlaylistDetailSerializer(serializers.ModelSerializer):
    """
    Serialize chi tiết playlist kèm danh sách bài hát phân trang.
    songs và song_count lấy từ context (được view truyền vào) thay vì
    tự query DB — view đã xử lý pagination và đếm riêng để hỗ trợ offset/limit.
    """
    songs = serializers.SerializerMethodField()
    song_count = serializers.SerializerMethodField()

    class Meta:
        model = Playlist
        fields = ['id', 'title', 'description', 'image_url', 'songs', 'song_count', 'created_at']

    def get_songs(self, obj):
        # context['song_qs'] là queryset đã được slice theo offset/limit từ view
        return PlaylistSongSerializer(self.context['song_qs'], many=True).data

    def get_song_count(self, obj):
        # Tổng số bài (không phải số bài trong page hiện tại)
        return self.context.get('song_count')


class PlaylistCreateSerializer(serializers.Serializer):
    """Validate dữ liệu khi tạo playlist mới."""
    title = serializers.CharField(required=True, max_length=255)
    description = serializers.CharField(required=False, allow_blank=True, default='')
    image_url = serializers.CharField(required=False, allow_blank=True, default='')


class PlaylistUpdateSerializer(serializers.Serializer):
    """Validate dữ liệu khi cập nhật playlist (partial update — không field nào bắt buộc)."""
    title = serializers.CharField(required=False, max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    image_url = serializers.CharField(required=False, allow_blank=True)


class AddSongSerializer(serializers.Serializer):
    """
    Validate dữ liệu khi thêm bài hát vào playlist.
    Nhận metadata bài hát để upsert vào bảng songs nếu chưa tồn tại,
    đảm bảo foreign key playlist_songs.song_id hợp lệ.
    """
    song_id = serializers.CharField(required=True)
    title = serializers.CharField(required=False, allow_blank=True, default='')
    subtitle = serializers.CharField(required=False, allow_blank=True, default='')
    image_url = serializers.CharField(required=False, allow_blank=True, default='')
    audio_url = serializers.CharField(required=False, allow_blank=True, default='')
    duration = serializers.IntegerField(required=False, allow_null=True, default=None)
    source = serializers.CharField(required=False, allow_blank=True, default='youtube')
