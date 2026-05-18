import hashlib
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Thread

logger = logging.getLogger(__name__)

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.db.models import F, Q
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.responses import (
    success, created,
    bad_request, forbidden, not_found,
    bad_gateway,
)
from core.pagination import paginate, parse_offset_limit
from services.nct import get_chart as nct_get_chart, resolve_audio as nct_resolve_audio, search as nct_search
from services.jamendo import JamendoError
from services.jamendo import search as jamendo_search
from services.jamendo import get_tracks_by_genre as jamendo_genre
from services.jamendo import get_discovery as jamendo_discovery
from services.youtube import YouTubeError, extract_audio_url, search_youtube, get_autocomplete
from services.youtube import convert_deezer_to_youtube, get_related_videos

from core.permissions import FREE_DOWNLOAD_LIMIT, FREE_SEARCH_LIMIT, FREE_HISTORY_DAYS, FREE_FAVORITE_LIMIT, is_premium

from .models import DownloadedSong, LikedSong, Lyric, PlayHistory, Song
from .serializers import (
    DownloadSongSerializer,
    DownloadedSongSerializer,
    LikedSongSerializer,
    LyricSerializer,
    PlayHistorySerializer,
    RecordPlaySerializer,
    ResolveAudioSerializer,
    SearchSerializer,
)


def _cache_key(prefix: str, *parts) -> str:
    """
    Tạo cache key an toàn từ nhiều thành phần.
    Hash SHA-256 để tránh cache key quá dài (Redis giới hạn key size)
    và tránh ký tự đặc biệt trong query string gây lỗi.
    """
    raw = '|'.join(str(part) for part in parts)
    digest = hashlib.sha256(raw.encode('utf-8')).hexdigest()
    return f'{prefix}:{digest}'


def _is_premium_cached(user_id: str) -> bool:
    """Cache trạng thái Premium 60s để tránh query bảng subscriptions mỗi request."""
    key = f'user-premium:{user_id}'
    cached = cache.get(key)
    if cached is not None:
        return cached
    premium = is_premium(user_id)
    cache.set(key, premium, timeout=60)
    return premium


def _normalize(s):
    """Chuẩn hóa chuỗi để so sánh dedup: bỏ ký tự đặc biệt, lowercase."""
    return re.sub(r'[^a-z0-9]', '', s.lower().strip()) if s else ''


# Regex kiểm tra YouTube video ID hợp lệ (11 ký tự alphanumeric + _ -)
_YOUTUBE_ID_RE = re.compile(r'^[A-Za-z0-9_-]{11}$')


def _background_save_results(results: list):
    """Lưu kết quả tìm kiếm từ API ngoài vào DB trong background thread."""
    from services.crawler import _save_songs
    _save_songs(results, 'search')


def _song_to_search_result(song: Song) -> dict:
    """
    Chuyển Song model thành dict cho search response.
    Dùng 'or' để null-safe: tránh trả None về client khi field trống.
    Không dùng SongSerializer ở đây vì serializer trả None thay vì ''.
    """
    return {
        'id': song.id,
        'title': song.title or '',
        'subtitle': song.subtitle or '',
        'image_url': song.image_url or '',
        'audio_url': song.audio_url,
        'album_name': song.album_name,
        'duration': song.duration,
        'source': song.source or 'youtube',
        'genre': song.genre,
        'region': song.region,
    }


def _is_playable_song(song: Song) -> bool:
    """
    Lọc bỏ bài hát không thực sự phát được để không hiển thị trong kết quả.
    - source='db'/'test' hoặc audio_url chứa 'example.com': dữ liệu test/fake
    - source='youtube': cần YouTube video ID hợp lệ (11 ký tự)
    - source='search_cache': chấp nhận nếu có audio_url hoặc YouTube ID hợp lệ
    - source='jamendo'/'nct'/'deezer_preview': luôn có thể phát (có audio_url thật)
    """
    source = (song.source or '').lower()
    audio_url = song.audio_url or ''
    if source in {'db', 'test'} or 'example.com' in audio_url:
        return False
    if source == 'youtube':
        return bool(_YOUTUBE_ID_RE.match(str(song.id)))
    if source == 'search_cache':
        return bool(audio_url) or bool(_YOUTUBE_ID_RE.match(str(song.id)))
    if source in {'jamendo', 'nct', 'deezer_preview'}:
        return True
    return bool(audio_url)


def _playable_results(qs, limit: int) -> list[dict]:
    """
    Lấy đủ limit bài hát phát được từ queryset.
    Query limit*5 record để có đủ bài sau khi lọc bỏ các bài không phát được,
    tránh phải query nhiều lần khi tỉ lệ bài không phát được cao.
    """
    results = []
    for song in qs[:limit * 5]:
        if not _is_playable_song(song):
            continue
        results.append(_song_to_search_result(song))
        if len(results) >= limit:
            break
    return results


def _dedupe_results(results: list[dict], limit: int | None = None) -> list[dict]:
    """
    Loại bỏ trùng lặp từ nhiều nguồn kết hợp.
    Key dedup: id nếu có, hoặc (normalized_title, normalized_subtitle).
    Bỏ qua bài không có title (metadata chưa đầy đủ).
    """
    seen = set()
    deduped = []
    for r in results:
        key = r.get('id') or (_normalize(r.get('title', '')), _normalize(r.get('subtitle', '')))
        if key not in seen and r.get('title'):
            seen.add(key)
            deduped.append(r)
            if limit and len(deduped) >= limit:
                break
    return deduped


def _db_search_results(query: str, limit: int) -> list[dict]:
    """
    Tìm kiếm bài hát trong DB nội bộ theo title, subtitle, album_name.
    Tách query thành token để OR search — ví dụ 'sơn tùng' tìm cả title và subtitle.
    Chỉ trả về bài hát có thể phát được (_is_playable_song).
    """
    terms = [term for term in re.split(r'\s+', query.strip()) if len(term) >= 2]
    token_query = Q()
    for term in terms:
        token_query |= Q(title__icontains=term) | Q(subtitle__icontains=term) | Q(album_name__icontains=term)
    query_filter = token_query or (
        Q(title__icontains=query)
        | Q(subtitle__icontains=query)
        | Q(album_name__icontains=query)
    )
    return _playable_results(Song.objects.filter(query_filter).order_by('-created_at'), limit)


def _db_genre_results(genre: str, limit: int) -> list[dict]:
    """Lấy bài hát theo thể loại từ DB (tìm chính xác theo genre, không phân biệt hoa thường)."""
    return _playable_results(Song.objects.filter(genre__iexact=genre).order_by('-created_at'), limit)


def _db_region_results(region: str, limit: int) -> list[dict]:
    """
    Lấy bài hát theo region/chart (v-pop, us-uk, k-pop, ...).
    Normalize dấu gạch ngang thành khoảng trắng và tìm cả trong genre
    vì một số bài hát lưu region dưới dạng genre.
    """
    normalized = region.replace('-', ' ')
    return _playable_results(
        Song.objects.filter(
            Q(region__iexact=region)
            | Q(region__iexact=normalized)
            | Q(genre__iexact=region)
            | Q(genre__iexact=normalized)
        ).order_by('-created_at'),
        limit,
    )


def _db_recent_results(limit: int) -> list[dict]:
    """Lấy bài hát mới nhất trong DB (dùng cho Trending section)."""
    return _playable_results(Song.objects.order_by('-created_at'), limit)


def _db_genres_map(genres: list[str], per_limit: int) -> dict[str, list[dict]]:
    """
    Lấy bài hát cho nhiều thể loại cùng lúc trong một query duy nhất.
    Query 300 bài gần nhất rồi phân nhóm theo genre — tránh N query riêng cho mỗi genre.
    """
    wanted = {genre.lower(): genre for genre in genres}
    grouped = {genre: [] for genre in genres}
    for song in Song.objects.filter(genre__isnull=False).order_by('-created_at')[:300]:
        if not _is_playable_song(song):
            continue
        key = (song.genre or '').lower()
        genre = wanted.get(key)
        if genre and len(grouped[genre]) < per_limit:
            grouped[genre].append(_song_to_search_result(song))
    return grouped


def _merge_db_first(db_results: list[dict], external_results: list[dict], limit: int) -> list[dict]:
    """
    Ghép kết quả DB và external, ưu tiên bài từ DB lên đầu.
    Dedup sau khi merge để loại bỏ trùng lặp giữa hai nguồn.
    """
    return _dedupe_results([*db_results, *external_results], limit)


def _can_call_jamendo() -> bool:
    """Chỉ gọi Jamendo API nếu đã cấu hình JAMENDO_CLIENT_ID trong settings."""
    return bool(settings.JAMENDO_CLIENT_ID)


def _include_total(request) -> bool:
    """
    Kiểm tra client có muốn nhận tổng số record không.
    Mặc định True. Client tắt bằng ?return_total=false để bỏ qua count query.
    """
    return request.query_params.get('return_total', 'true').lower() not in {'0', 'false', 'no'}


def _cached_count(key: str, qs, timeout: int = 30) -> int:
    """Cache kết quả .count() ngắn hạn để tránh query DB khi paginate."""
    cached = cache.get(key)
    if cached is not None:
        return cached
    count = qs.count()
    cache.set(key, count, timeout=timeout)
    return count


def _user_list_version(user_id: str, list_name: str) -> int:
    """Lấy version hiện tại của list (history/favorites/downloads) để dùng trong cache key."""
    return cache.get(f'{list_name}-version:{user_id}') or 1


def _bump_user_list_version(user_id: str, list_name: str):
    """
    Tăng version của list → tự động invalidate tất cả cache page cũ của list đó.
    Cơ chế: cache key nhúng version, bump version làm key cũ không bao giờ hit nữa.
    """
    key = f'{list_name}-version:{user_id}'
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 2, timeout=None)


class ResolveAudioView(APIView):
    """
    POST /resolve-audio/ — Lấy audio stream URL cho bài hát.
    Hỗ trợ nhiều nguồn:
    - YouTube video_id/youtube_id: extract trực tiếp từ YouTube
    - NCT URL: lấy stream từ NCT
    - title + artist: tìm YouTube match rồi extract
    Kết quả cache 1h vì audio URL YouTube có TTL (~6h nhưng cache ngắn hơn để an toàn).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ResolveAudioSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        video_id = data.get('video_id') or data.get('youtube_id')
        resolve_cache_key = _cache_key(
            'resolve:v2',
            video_id or '',
            data.get('nct_url') or '',
            data.get('title') or '',
            data.get('artist') or '',
        )
        cached = cache.get(resolve_cache_key)
        if cached:
            return success(cached)

        if video_id:
            try:
                result = extract_audio_url(video_id)
                data = {
                    'youtube_id': video_id,
                    'audio_url': result['audio_url'],
                    'expires_at': result['expires_at'],
                    'title': result.get('title'),
                    'duration': result.get('duration'),
                }
                cache.set(resolve_cache_key, data, timeout=3600)
                return success(data)
            except YouTubeError as e:
                logger.warning('YouTube extract failed for video_id %s: %s', video_id, e)
                return bad_gateway(str(e))

        nct_url = data.get('nct_url')
        if nct_url:
            result = nct_resolve_audio(nct_url)
            if not result:
                return not_found('Could not resolve NCT audio')
            data = {'audio_url': result['audio_url'], 'source': 'nct'}
            cache.set(resolve_cache_key, data, timeout=3600)
            return success(data)

        title = data.get('title')
        artist = data.get('artist', '')

        if title:
            try:
                # Tìm YouTube video phù hợp nhất với title + artist
                yt_data = convert_deezer_to_youtube(title, artist)
                if not yt_data:
                    return not_found('Could not find YouTube match')
                audio = extract_audio_url(yt_data['id'])
                data = {
                    'youtube_id': yt_data['id'],
                    'audio_url': audio['audio_url'],
                    'expires_at': audio['expires_at'],
                    'title': audio.get('title', title),
                    'duration': audio.get('duration'),
                }
                cache.set(resolve_cache_key, data, timeout=3600)
                return success(data)
            except YouTubeError as e:
                logger.warning('YouTube resolve failed for title "%s": %s', title, e)
                return bad_gateway(str(e))

        return bad_request('Provide video_id, youtube_id, or title')


class SearchView(APIView):
    """
    GET /search/?q=...&limit=10&sources=youtube,jamendo,nct
    Chiến lược tìm kiếm:
      1. DB-first: tìm trong nội bộ — nhanh, không tốn API quota
      2. Nếu DB trống → gọi song song YouTube/Jamendo/NCT bằng ThreadPoolExecutor
      3. Lưu kết quả API ngoài vào DB background (để lần sau có trong DB)
    Free tier chỉ nhận tối đa FREE_SEARCH_LIMIT kết quả.
    Cache 5 phút để tránh gọi lặp API ngoài với cùng query.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = SearchSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        params = serializer.validated_data

        query = params['q']
        limit = params['limit']
        sources = params['sources'].split(',')
        premium = _is_premium_cached(str(request.user.id))
        # Cache key bao gồm premium status vì Free và Premium nhận số kết quả khác nhau
        cache_key = _cache_key('search:v5', query.strip().lower(), limit, params['sources'], premium)
        cached = cache.get(cache_key)
        if cached:
            return success(cached)

        db_results = _db_search_results(query, limit)
        if db_results:
            deduped = _dedupe_results(db_results, limit)
            truncated = False
            if not premium:
                truncated = len(deduped) > FREE_SEARCH_LIMIT
                deduped = deduped[:FREE_SEARCH_LIMIT]
            data = {
                'results': deduped[:limit],
                'total': len(deduped),
                'truncated': truncated,
                'errors': None,
            }
            cache.set(cache_key, data, timeout=300)
            return success(data)

        # Gọi song song các API ngoài để giảm tổng thời gian chờ
        futures = {}
        errors = []

        with ThreadPoolExecutor(max_workers=3) as ex:
            if 'youtube' in sources:
                futures['youtube'] = ex.submit(search_youtube, query, limit)
            if 'jamendo' in sources:
                futures['jamendo'] = ex.submit(jamendo_search, query, limit)
            if 'nct' in sources:
                futures['nct'] = ex.submit(nct_search, query, limit)

        external_results = []
        for name, future in futures.items():
            try:
                external_results.extend(future.result())
            except YouTubeError as e:
                logger.warning('Search source youtube failed for query "%s": %s', query, e)
                errors.append(f'youtube: {e}')
            except JamendoError as e:
                logger.warning('Search source jamendo failed for query "%s": %s', query, e)
                errors.append(f'jamendo: {e}')
            except Exception as e:
                logger.error('Search source %s failed unexpectedly for query "%s"', name, query, exc_info=True)
                errors.append(f'{name}: failed')

        # Lưu kết quả API ngoài vào DB ở background để lần sau tìm được từ DB
        if external_results:
            Thread(target=_background_save_results, args=(external_results,), daemon=True).start()

        deduped = _merge_db_first(db_results, external_results, limit)
        truncated = False
        if not premium:
            truncated = len(deduped) > FREE_SEARCH_LIMIT
            deduped = deduped[:FREE_SEARCH_LIMIT]

        data = {
            'results': deduped[:limit],
            'total': len(deduped),
            'truncated': truncated,
            'errors': errors if errors else None,
        }
        cache.set(cache_key, data, timeout=300)
        return success(data)


class AutocompleteView(APIView):
    """
    GET /autocomplete/?q=... — Gợi ý từ khóa tìm kiếm từ YouTube autocomplete API.
    Bỏ qua query dưới 2 ký tự để tránh request vô nghĩa.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        q = request.query_params.get('q', '')
        if not q or len(q) < 2:
            return success({'suggestions': []})
        return success({'suggestions': get_autocomplete(q)})


class HomeFeedView(APIView):
    """
    GET /home-feed/ — Trang chủ: trending + genres (cho tất cả) + charts (chỉ Premium).
    Cache riêng cho Free và Premium vì nội dung khác nhau.
    Chiến lược: DB trước, gọi Jamendo/NCT nếu DB chưa có đủ dữ liệu.
    Cache 30 phút — đủ lâu để tránh gọi API ngoài liên tục.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        premium = _is_premium_cached(str(request.user.id))
        cache_key = f'home_feed:{"premium" if premium else "free"}:v4'
        cached = cache.get(cache_key)
        if cached:
            return success(cached)

        genres = {}
        genre_slugs = ['rock', 'pop', 'hip-hop', 'electronic', 'jazz', 'folk']
        # Lấy tất cả genres trong một query DB thay vì N query riêng
        db_genres = _db_genres_map(genre_slugs, 10)
        for genre in genre_slugs:
            db_tracks = db_genres.get(genre, [])
            external_tracks = []
            try:
                if not db_tracks and _can_call_jamendo():
                    external_tracks = jamendo_genre(genre, 10)
            except JamendoError as e:
                logger.warning('Jamendo genre fetch failed for genre "%s": %s', genre, e)
                external_tracks = []
            genres[genre] = _merge_db_first(db_tracks, external_tracks, 10)

        trending = _db_recent_results(20)
        try:
            if not trending and _can_call_jamendo():
                trending = jamendo_discovery(20)
        except JamendoError as e:
            logger.warning('Jamendo discovery failed: %s', e)

        if not premium:
            # Free tier không có charts
            data = {'trending': trending, 'genres': genres}
            cache.set(cache_key, data, timeout=1800)
            return success(data)

        # Premium: thêm charts theo region
        charts = {}
        chart_regions = ['v-pop', 'us-uk', 'k-pop', 'v-rap', 'billboard']
        for region in chart_regions:
            db_tracks = _db_region_results(region, 20)
            external_tracks = []
            try:
                if not db_tracks:
                    external_tracks = nct_get_chart(region)
            except Exception as e:
                logger.warning('NCT chart fetch failed for region "%s": %s', region, e, exc_info=True)
                external_tracks = []
            charts[region] = _merge_db_first(db_tracks, external_tracks, 20)

        data = {'trending': trending, 'charts': charts, 'genres': genres}
        cache.set(cache_key, data, timeout=1800)
        return success(data)


class ChartDetailView(APIView):
    """
    GET /charts/?region=v-pop — Chi tiết chart theo region (chỉ Premium).
    DB-first: tìm trong nội bộ theo region/genre, fallback về NCT chart API.
    Cache 30 phút.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _is_premium_cached(str(request.user.id)):
            return forbidden('Charts are a Premium feature. Upgrade to access full chart details.')

        region = request.query_params.get('region', '')
        if not region:
            return bad_request('region parameter is required')

        cache_key = _cache_key('chart:v2', region.lower().strip())
        cached = cache.get(cache_key)
        if cached:
            return success(cached)

        db_tracks = _db_region_results(region, 20)
        external_tracks = []
        if not db_tracks:
            try:
                external_tracks = nct_get_chart(region)
            except Exception as e:
                logger.warning('NCT chart fetch failed for region "%s": %s', region, e, exc_info=True)
        tracks = _merge_db_first(db_tracks, external_tracks, 20)
        data = {'region': region, 'tracks': tracks}
        cache.set(cache_key, data, timeout=1800)
        return success(data)


class GenreTrackListView(APIView):
    """
    GET /genres/?genre=pop — Danh sách bài hát theo thể loại.
    Premium nhận 20 bài, Free nhận 10 bài.
    truncated=True thông báo cho client biết có thêm bài nếu upgrade.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        genre = request.query_params.get('genre', '')
        if not genre:
            return bad_request('genre parameter is required')

        try:
            premium = _is_premium_cached(str(request.user.id))
            limit = 20 if premium else 10
            cache_key = _cache_key('genre:v2', genre.lower().strip(), limit)
            cached = cache.get(cache_key)
            if cached:
                return success(cached)

            db_tracks = _db_genre_results(genre, limit)
            external_tracks = []
            if not db_tracks and _can_call_jamendo():
                try:
                    external_tracks = jamendo_genre(genre, limit)
                except JamendoError as e:
                    logger.warning('Jamendo genre tracks failed for genre "%s": %s', genre, e)
                    return bad_gateway(str(e))
            tracks = _merge_db_first(db_tracks, external_tracks, limit)
            data = {
                'genre': genre,
                'tracks': tracks,
                'truncated': not premium and len(tracks) >= limit,
            }
            cache.set(cache_key, data, timeout=1800)
            return success(data)
        except Exception:
            logger.exception('Unexpected error in GenreTrackListView for genre "%s"', genre)
            from core.responses import server_error
            return server_error()


class RecordPlayView(APIView):
    """
    POST /record-play/ — Ghi nhận lượt nghe bài hát.
    Upsert pattern: nếu đã nghe trước đó thì tăng count, nếu chưa thì tạo mới.
    PostgreSQL: dùng raw SQL ON CONFLICT để atomic upsert không race condition.
    Fallback ORM cho DB khác (SQLite khi test local).
    Chỉ tính lượt nghe khi progress_percent >= 50 (validate ở serializer).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = RecordPlaySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        song_id = data['song_id']

        # Upsert song vào bảng songs để FK trong play_history hợp lệ
        Song.objects.get_or_create(
            id=song_id,
            defaults={
                'title': data.get('title', ''),
                'subtitle': data.get('subtitle', ''),
                'image_url': data.get('image_url', ''),
                'duration': data.get('duration'),
                'source': 'youtube',
            },
        )

        now = timezone.now()
        if connection.vendor == 'postgresql':
            # PostgreSQL: ON CONFLICT DO UPDATE đảm bảo atomicity khi nhiều request đồng thời
            with connection.cursor() as cursor:
                cursor.execute(
                    '''
                    INSERT INTO play_history (user_id, song_id, count, last_played)
                    VALUES (%s, %s, 1, %s)
                    ON CONFLICT (user_id, song_id)
                    DO UPDATE SET count = play_history.count + 1, last_played = EXCLUDED.last_played
                    RETURNING count
                    ''',
                    [str(request.user.id), song_id, now],
                )
                count = cursor.fetchone()[0]
        else:
            # Fallback ORM cho SQLite (dev/test)
            history, created_obj = PlayHistory.objects.get_or_create(
                user=request.user,
                song_id=song_id,
                defaults={'count': 1, 'last_played': now},
            )
            if created_obj:
                count = history.count
            else:
                PlayHistory.objects.filter(pk=history.pk).update(
                    count=F('count') + 1,
                    last_played=now,
                )
                history.refresh_from_db()
                count = history.count

        cache.delete(f'history-count:{request.user.id}')
        cache.delete(f'user-stats:{request.user.id}')
        _bump_user_list_version(str(request.user.id), 'history')
        return success({'count': count}, message='Play recorded')


class PlayHistoryView(APIView):
    """
    GET    /history/ — Danh sách lịch sử nghe của user (phân trang, mới nhất trước).
    DELETE /history/ — Xóa một entry (song_id param) hoặc toàn bộ lịch sử.
    Free tier chỉ xem được lịch sử trong FREE_HISTORY_DAYS ngày gần nhất.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        offset, limit = parse_offset_limit(request)

        qs = PlayHistory.objects.filter(user=request.user)\
            .select_related('song')\
            .order_by('-last_played')

        if not _is_premium_cached(str(request.user.id)):
            # Free tier: giới hạn lịch sử theo thời gian
            cutoff = timezone.now() - timedelta(days=FREE_HISTORY_DAYS)
            qs = qs.filter(last_played__gte=cutoff)

        # Version nhúng vào cache key để tự invalidate khi có bài mới được ghi
        cache_key = _cache_key(
            'history-page:v1',
            request.user.id,
            _user_list_version(str(request.user.id), 'history'),
            offset,
            limit,
            _include_total(request),
        )
        cached = cache.get(cache_key)
        if cached:
            return success(cached)

        total = _cached_count(f'history-count:{request.user.id}', qs) if _include_total(request) else None
        items = PlayHistorySerializer(qs[offset:offset + limit], many=True).data
        data = paginate(items, offset, limit, total)
        cache.set(cache_key, data, timeout=60)
        return success(data)

    def delete(self, request):
        song_id = request.query_params.get('song_id')
        qs = PlayHistory.objects.filter(user=request.user)

        if song_id:
            deleted, _ = qs.filter(song_id=song_id).delete()
            if deleted == 0:
                return not_found('History entry not found')
            cache.delete(f'history-count:{request.user.id}')
            cache.delete(f'user-stats:{request.user.id}')
            _bump_user_list_version(str(request.user.id), 'history')
            return success(message='History entry deleted')
        else:
            # Không có song_id → xóa toàn bộ lịch sử
            qs.delete()
            cache.delete(f'history-count:{request.user.id}')
            cache.delete(f'user-stats:{request.user.id}')
            _bump_user_list_version(str(request.user.id), 'history')
            return success(message='All history cleared')


class TopPlayedView(APIView):
    """
    GET /top-played/?limit=10 — Bài hát nghe nhiều nhất của user.
    Sắp xếp theo count giảm dần. Free tier giới hạn theo ngày (FREE_HISTORY_DAYS).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        limit = int(request.query_params.get('limit', 10))

        qs = PlayHistory.objects.filter(user=request.user)\
            .select_related('song')\
            .order_by('-count')

        if not _is_premium_cached(str(request.user.id)):
            cutoff = timezone.now() - timedelta(days=FREE_HISTORY_DAYS)
            qs = qs.filter(last_played__gte=cutoff)

        return success({'top': PlayHistorySerializer(qs[:limit], many=True).data})


class FavoriteToggleView(APIView):
    """
    POST /favorites/<song_id>/ — Thêm/bỏ bài hát khỏi yêu thích.
    Body: {"liked": true/false}
    Free tier giới hạn tối đa FREE_FAVORITE_LIMIT bài yêu thích.
    get_or_create để tránh lỗi duplicate khi click nhanh.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, song_id):
        liked = request.data.get('liked', True)

        if liked:
            # Kiểm tra giới hạn trước khi thêm (chỉ Free tier)
            if not _is_premium_cached(str(request.user.id)):
                current_count = LikedSong.objects.filter(user=request.user).count()
                if current_count >= FREE_FAVORITE_LIMIT:
                    return forbidden(
                        f'Favorite limit reached ({FREE_FAVORITE_LIMIT}). Upgrade to Premium for unlimited favorites.'
                    )
            LikedSong.objects.get_or_create(
                user=request.user,
                song_id=song_id,
                defaults={'liked_at': timezone.now()},
            )
            cache.delete(f'favorites-count:{request.user.id}')
            cache.delete(f'user-stats:{request.user.id}')
            _bump_user_list_version(str(request.user.id), 'favorites')
            return success({'liked': True}, message='Added to favorites')
        else:
            LikedSong.objects.filter(user=request.user, song_id=song_id).delete()
            cache.delete(f'favorites-count:{request.user.id}')
            cache.delete(f'user-stats:{request.user.id}')
            _bump_user_list_version(str(request.user.id), 'favorites')
            return success({'liked': False}, message='Removed from favorites')


class FavoriteListView(APIView):
    """
    GET /favorites/ — Danh sách bài hát yêu thích, mới nhất trước (phân trang).
    Cache theo version để tự invalidate khi thêm/bỏ yêu thích.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        offset, limit = parse_offset_limit(request)

        qs = LikedSong.objects.filter(user=request.user)\
            .select_related('song')\
            .order_by('-liked_at')
        cache_key = _cache_key(
            'favorites-page:v1',
            request.user.id,
            _user_list_version(str(request.user.id), 'favorites'),
            offset,
            limit,
            _include_total(request),
        )
        cached = cache.get(cache_key)
        if cached:
            return success(cached)

        total = _cached_count(f'favorites-count:{request.user.id}', qs) if _include_total(request) else None
        items = LikedSongSerializer(qs[offset:offset + limit], many=True).data
        data = paginate(items, offset, limit, total)
        cache.set(cache_key, data, timeout=60)
        return success(data)


class DownloadSongView(APIView):
    """
    POST   /downloads/<song_id>/ — Đánh dấu bài hát đã download (offline).
    DELETE /downloads/<song_id>/ — Xóa khỏi danh sách download.

    POST flow:
      1. Upsert song vào bảng songs
      2. Kiểm tra đã download chưa (trả về idempotent response nếu rồi)
      3. Kiểm tra quota download (Free tier)
      4. Tạo DownloadedSong record
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, song_id):
        serializer = DownloadSongSerializer(data={'song_id': song_id, **request.data})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Upsert song trước để FK hợp lệ
        Song.objects.get_or_create(
            id=song_id,
            defaults={
                'title': data.get('title', ''),
                'subtitle': data.get('subtitle', ''),
                'image_url': data.get('image_url', ''),
                'audio_url': data.get('audio_url', ''),
                'duration': data.get('duration'),
                'source': data.get('source', ''),
            },
        )

        # Idempotent: nếu đã download rồi thì trả về info mà không tính quota thêm
        already = DownloadedSong.objects.filter(user=request.user, song_id=song_id).first()
        if already:
            return success({'downloaded_at': already.downloaded_at}, message='Song already downloaded')

        # Kiểm tra quota sau khi biết chắc chưa download (tránh đếm sai)
        if not _is_premium_cached(str(request.user.id)):
            current_count = DownloadedSong.objects.filter(user=request.user).count()
            if current_count >= FREE_DOWNLOAD_LIMIT:
                return forbidden(
                    f'Download limit reached ({FREE_DOWNLOAD_LIMIT}). Upgrade to Premium for unlimited downloads.'
                )

        downloaded = DownloadedSong.objects.create(user=request.user, song_id=song_id)
        cache.delete(f'downloads-count:{request.user.id}')
        _bump_user_list_version(str(request.user.id), 'downloads')
        return created({'downloaded_at': downloaded.downloaded_at}, message='Song downloaded')

    def delete(self, request, song_id):
        deleted, _ = DownloadedSong.objects.filter(user=request.user, song_id=song_id).delete()
        if deleted == 0:
            return not_found('Downloaded song not found')
        cache.delete(f'downloads-count:{request.user.id}')
        _bump_user_list_version(str(request.user.id), 'downloads')
        return success(message='Download removed')


class DownloadedSongsView(APIView):
    """
    GET /downloads/ — Danh sách bài hát đã download (phân trang, mới nhất trước).
    Cache theo version để tự invalidate khi thêm/xóa download.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        offset, limit = parse_offset_limit(request)

        qs = DownloadedSong.objects.filter(user=request.user)\
            .select_related('song')\
            .order_by('-downloaded_at')
        cache_key = _cache_key(
            'downloads-page:v1',
            request.user.id,
            _user_list_version(str(request.user.id), 'downloads'),
            offset,
            limit,
            _include_total(request),
        )
        cached = cache.get(cache_key)
        if cached:
            return success(cached)

        total = _cached_count(f'downloads-count:{request.user.id}', qs) if _include_total(request) else None
        items = DownloadedSongSerializer(qs[offset:offset + limit], many=True).data
        data = paginate(items, offset, limit, total)
        cache.set(cache_key, data, timeout=60)
        return success(data)


class RelatedView(APIView):
    """
    GET /related/<song_id>/ — Bài hát liên quan.
    Chiến lược:
      1. Tìm trong DB theo title + subtitle của bài đang xem
      2. Nếu DB không có → gọi YouTube related videos (nếu là YouTube ID)
         hoặc search YouTube theo title
    Cache 30 phút.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, song_id):
        limit = int(request.query_params.get('limit', 10))
        cache_key = _cache_key('related:v2', song_id, limit)
        cached = cache.get(cache_key)
        if cached:
            return success(cached)

        song = Song.objects.filter(id=song_id).first()
        db_results = []

        if song and song.title:
            # Tìm bài tương tự trong DB theo title+subtitle, loại bỏ chính bài đó
            db_results = _db_search_results(f'{song.title} {song.subtitle or ""}', limit + 1)
            db_results = [r for r in db_results if r['id'] != song_id]
            if db_results:
                results = _dedupe_results(db_results, limit)
                data = {'results': results, 'total': len(results)}
                cache.set(cache_key, data, timeout=1800)
                return success(data)

        external_results = []
        try:
            if _YOUTUBE_ID_RE.match(song_id):
                # YouTube ID hợp lệ → dùng YouTube related videos API
                external_results = get_related_videos(song_id, limit)
            elif song and song.title:
                # Không có YouTube ID → search YouTube theo tên bài
                external_results = search_youtube(f'{song.title} {song.subtitle or ""}', limit)
        except YouTubeError as e:
            logger.warning('YouTube related/search failed for song_id %s: %s', song_id, e)
            external_results = []

        results = _merge_db_first(db_results, external_results, limit)
        data = {'results': results, 'total': len(results)}
        cache.set(cache_key, data, timeout=1800)
        return success(data)


class LyricsView(APIView):
    """
    GET /lyrics/<song_id>/ — Lấy lời bài hát.
    Nếu không có trong DB, tự động fetch từ API ngoài (lrclib, genius, ...)
    và lưu lại vào DB (fetch_and_store_lyrics).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, song_id):
        try:
            lyric = Lyric.objects.get(pk=song_id)
        except Lyric.DoesNotExist:
            # Lazy fetch: chỉ gọi API ngoài khi cần, kết quả lưu vào DB cho lần sau
            try:
                from services.lyrics import fetch_and_store_lyrics
                lyric = fetch_and_store_lyrics(song_id)
            except Exception:
                logger.exception('fetch_and_store_lyrics failed for song_id %s', song_id)
                from core.responses import server_error
                return server_error('Failed to fetch lyrics')
            if not lyric:
                return not_found('Lyrics not available for this song')
        return success(LyricSerializer(lyric).data)


class DownloadQuotaView(APIView):
    """
    GET /download-quota/ — Kiểm tra quota download của user.
    Trả về: is_premium, số lượt đã dùng, giới hạn (None = unlimited cho Premium).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        premium = _is_premium_cached(str(request.user.id))
        current_count = _cached_count(
            f'downloads-count:{request.user.id}',
            DownloadedSong.objects.filter(user=request.user),
        )
        return success({
            'is_premium': premium,
            'downloads_used': current_count,
            'downloads_limit': None if premium else FREE_DOWNLOAD_LIMIT,
        })
