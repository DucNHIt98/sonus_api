import logging

from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, Max
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

from core.permissions import FREE_PLAYLIST_LIMIT, is_premium
from core.responses import success, created, no_content, bad_request, forbidden, not_found
from core.pagination import paginate, parse_offset_limit
from music.models import Song

from .models import Playlist, PlaylistSong
from .serializers import (
    AddSongSerializer,
    PlaylistCreateSerializer,
    PlaylistDetailSerializer,
    PlaylistListSerializer,
    PlaylistUpdateSerializer,
)


def _include_total(request) -> bool:
    """
    Kiểm tra client có muốn nhận tổng số record không.
    Mặc định trả về True. Client có thể tắt bằng ?return_total=false
    để tiết kiệm một DB count query khi không cần thiết.
    """
    return request.query_params.get('return_total', 'true').lower() not in {'0', 'false', 'no'}


def _cached_count(key: str, qs, timeout: int = 30) -> int:
    """
    Đếm số record với cache ngắn hạn (mặc định 30s).
    Tránh gọi .count() mỗi request khi danh sách ít thay đổi.
    """
    cached = cache.get(key)
    if cached is not None:
        return cached
    count = qs.count()
    cache.set(key, count, timeout=timeout)
    return count


def _is_premium_cached(user_id: str) -> bool:
    """Cache kết quả kiểm tra Premium 60s để tránh query DB subscription mỗi request."""
    key = f'user-premium:{user_id}'
    cached = cache.get(key)
    if cached is not None:
        return cached
    premium = is_premium(user_id)
    cache.set(key, premium, timeout=60)
    return premium


def _list_version(key: str) -> int:
    """
    Lấy version hiện tại của một danh sách trong cache.
    Version được nhúng vào cache key để tự động invalidate trang cũ
    khi danh sách thay đổi (thêm/xóa/sửa playlist).
    """
    return cache.get(key) or 1


def _bump_list_version(key: str):
    """
    Tăng version của danh sách → tất cả cache key cũ chứa version cũ sẽ miss.
    Dùng cache.incr() nếu key tồn tại; nếu không thì set = 2 (1 là giá trị mặc định).
    """
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 2, timeout=None)


class PlaylistListView(APIView):
    """
    GET  /playlists/  — Danh sách playlist của user (phân trang offset/limit).
    POST /playlists/  — Tạo playlist mới (giới hạn FREE_PLAYLIST_LIMIT cho tài khoản Free).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        offset, limit = parse_offset_limit(request)

        # annotate song_count để PlaylistListSerializer đọc trực tiếp, không query N+1
        qs = Playlist.objects.filter(user=request.user)\
            .annotate(song_count=Count('playlistsong'))\
            .order_by('-created_at')
        include_total = _include_total(request)

        # Cache key nhúng version để tự invalidate khi playlist thay đổi
        cache_key = (
            f'playlists-page:{request.user.id}:'
            f'{_list_version(f"playlists-version:{request.user.id}")}:{offset}:{limit}:{include_total}'
        )
        cached = cache.get(cache_key)
        if cached:
            return success(cached)

        total = _cached_count(f'playlists-count:{request.user.id}', qs) if include_total else None
        items = PlaylistListSerializer(qs[offset:offset + limit], many=True).data
        data = paginate(items, offset, limit, total)
        cache.set(cache_key, data, timeout=60)
        return success(data)

    def post(self, request):
        # Kiểm tra giới hạn playlist trước khi tạo (chỉ áp dụng cho Free tier)
        if not _is_premium_cached(str(request.user.id)):
            current_count = Playlist.objects.filter(user=request.user).count()
            if current_count >= FREE_PLAYLIST_LIMIT:
                return forbidden(
                    f'Playlist limit reached ({FREE_PLAYLIST_LIMIT}). Upgrade to Premium for unlimited playlists.'
                )

        serializer = PlaylistCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        playlist = Playlist.objects.create(
            user=request.user,
            title=serializer.validated_data['title'],
            description=serializer.validated_data.get('description', ''),
            image_url=serializer.validated_data.get('image_url', ''),
            created_at=timezone.now(),
        )
        # Xóa cache count và bump version để GET list tự invalidate
        cache.delete(f'playlists-count:{request.user.id}')
        cache.delete(f'user-stats:{request.user.id}')
        _bump_list_version(f'playlists-version:{request.user.id}')

        # Playlist mới tạo chưa có annotation từ DB, gán thủ công để serializer đọc được
        playlist.song_count = 0
        return created(PlaylistListSerializer(playlist).data, message='Playlist created')


class PlaylistDetailView(APIView):
    """
    GET   /playlists/<pk>/  — Chi tiết playlist kèm bài hát phân trang.
    PATCH /playlists/<pk>/  — Cập nhật title/description/image_url.
    DELETE /playlists/<pk>/ — Xóa playlist.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        offset, limit = parse_offset_limit(request, default_limit=50)

        try:
            playlist = Playlist.objects.get(id=pk, user=request.user)
        except Playlist.DoesNotExist:
            return not_found('Playlist not found')

        include_total = _include_total(request)
        cache_key = (
            f'playlist-detail:{request.user.id}:{playlist.id}:'
            f'{_list_version(f"playlist-detail-version:{playlist.id}")}:{offset}:{limit}:{include_total}'
        )
        cached = cache.get(cache_key)
        if cached:
            return success(cached)

        # select_related('song') để tránh N+1 query khi PlaylistSongSerializer đọc song.xxx
        song_qs = PlaylistSong.objects.filter(playlist=playlist)\
            .select_related('song')\
            .order_by('position')[offset:offset + limit]
        total_songs_qs = PlaylistSong.objects.filter(playlist=playlist)
        total_songs = _cached_count(f'playlist-songs-count:{playlist.id}', total_songs_qs) if include_total else None

        # Truyền song_qs và song_count qua context để serializer dùng (không tự query)
        data = PlaylistDetailSerializer(
            playlist,
            context={'song_qs': song_qs, 'song_count': total_songs},
        ).data
        cache.set(cache_key, data, timeout=60)
        return success(data)

    def patch(self, request, pk):
        serializer = PlaylistUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        try:
            playlist = Playlist.objects.get(id=pk, user=request.user)
        except Playlist.DoesNotExist:
            return not_found('Playlist not found')

        for field in ('title', 'description', 'image_url'):
            if field in serializer.validated_data:
                setattr(playlist, field, serializer.validated_data[field])

        if not any(f in serializer.validated_data for f in ('title', 'description', 'image_url')):
            return bad_request('No fields to update')

        playlist.save()
        # Gán song_count thủ công vì instance từ .get() không có annotation
        playlist.song_count = _cached_count(f'playlist-songs-count:{playlist.id}', PlaylistSong.objects.filter(playlist=playlist))
        _bump_list_version(f'playlists-version:{request.user.id}')
        _bump_list_version(f'playlist-detail-version:{playlist.id}')

        return success(PlaylistListSerializer(playlist).data, message='Playlist updated')

    def delete(self, request, pk):
        deleted, _ = Playlist.objects.filter(id=pk, user=request.user).delete()
        if deleted == 0:
            return not_found('Playlist not found')
        # Xóa cache count và detail, bump cả hai version
        cache.delete(f'playlists-count:{request.user.id}')
        cache.delete(f'playlist-songs-count:{pk}')
        cache.delete(f'user-stats:{request.user.id}')
        _bump_list_version(f'playlists-version:{request.user.id}')
        _bump_list_version(f'playlist-detail-version:{pk}')
        return no_content()


class PlaylistSongManageView(APIView):
    """
    POST   /playlists/<pk>/songs/           — Thêm bài hát vào playlist.
    DELETE /playlists/<pk>/songs/<song_id>/ — Xóa bài hát khỏi playlist.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            playlist = Playlist.objects.get(id=pk, user=request.user)
        except Playlist.DoesNotExist:
            return not_found('Playlist not found')

        serializer = AddSongSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        song_id = data['song_id']

        if PlaylistSong.objects.filter(playlist=playlist, song_id=song_id).exists():
            return success(message='Song already in playlist')

        # Lấy position cao nhất hiện tại rồi +1, đảm bảo bài mới luôn ở cuối
        max_pos = PlaylistSong.objects.filter(playlist=playlist)\
            .aggregate(max_pos=Max('position'))['max_pos'] or 0

        # Upsert song vào bảng songs để đảm bảo FK hợp lệ trước khi tạo playlist_songs
        Song.objects.get_or_create(
            id=song_id,
            defaults={
                'title': data.get('title', ''),
                'subtitle': data.get('subtitle', ''),
                'image_url': data.get('image_url', ''),
                'audio_url': data.get('audio_url', ''),
                'duration': data.get('duration'),
                'source': data.get('source') or 'youtube',
            },
        )

        PlaylistSong.objects.create(
            playlist=playlist,
            song_id=song_id,
            position=max_pos + 1,
            created_at=timezone.now(),
        )
        cache.delete(f'playlist-songs-count:{pk}')
        _bump_list_version(f'playlist-detail-version:{pk}')

        return created({'position': max_pos + 1}, message='Song added to playlist')

    def delete(self, request, pk, song_id):
        deleted, _ = PlaylistSong.objects.filter(
            playlist__id=pk, playlist__user=request.user, song_id=song_id,
        ).delete()
        if deleted == 0:
            return not_found('Song not in playlist')
        cache.delete(f'playlist-songs-count:{pk}')
        _bump_list_version(f'playlist-detail-version:{pk}')
        return success(message='Song removed from playlist')


class PlaylistReorderView(APIView):
    """
    PATCH /playlists/<pk>/reorder/ — Đổi thứ tự bài hát trong playlist.
    Nhận song_ids (list) theo thứ tự mới; index trong list = position mới.
    Dùng bulk_update trong atomic transaction để tránh race condition.
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        song_ids = request.data.get('song_ids', [])
        if not isinstance(song_ids, list) or len(song_ids) < 2:
            return bad_request('song_ids must be a list with at least 2 items')

        try:
            Playlist.objects.get(id=pk, user=request.user)
        except Playlist.DoesNotExist:
            return not_found('Playlist not found')

        # Tạo map {song_id: new_position} từ thứ tự trong list gửi lên
        position_by_song = {song_id: idx for idx, song_id in enumerate(song_ids)}
        with transaction.atomic():
            playlist_songs = list(PlaylistSong.objects.filter(playlist_id=pk, song_id__in=song_ids))
            for playlist_song in playlist_songs:
                playlist_song.position = position_by_song[playlist_song.song_id]
            PlaylistSong.objects.bulk_update(playlist_songs, ['position'])
        _bump_list_version(f'playlist-detail-version:{pk}')

        return success({'song_ids': song_ids}, message='Playlist reordered')
