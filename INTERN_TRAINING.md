# Sonus API — Tài liệu Training Intern (Chuyên Sâu)

> **Mục tiêu:** Giúp intern nắm vững kiến trúc, nguyên tắc thiết kế, và quy ước code để có thể nhận task độc lập và đưa ra quyết định đúng khi gặp tình huống thực tế.

---

## Mục lục

1. [Tổng quan và Design Patterns](#1-tổng-quan-và-design-patterns)
2. [Docker — Image, Container, và Setup](#2-docker--image-container-và-setup)
3. [JSON Response chuẩn](#3-json-response-chuẩn)
4. [Error Handling — Nguyên tắc và Chuẩn](#4-error-handling--nguyên-tắc-và-chuẩn)
5. [Logging — Xem ở đâu, Viết như thế nào](#5-logging--xem-ở-đâu-viết-như-thế-nào)
6. [Serializer — Nguyên tắc và Quy chuẩn](#6-serializer--nguyên-tắc-và-quy-chuẩn)
7. [Cache — Cấu trúc, Lưu, và Xóa](#7-cache--cấu-trúc-lưu-và-xóa)
8. [Authentication — Token, Bảo mật, Vòng đời](#8-authentication--token-bảo-mật-vòng-đời)
9. [Authorization — Phân quyền Free/Premium](#9-authorization--phân-quyền-freepremium)
10. [Database — Patterns và Best Practices](#10-database--patterns-và-best-practices)
11. [Testing Setup](#11-testing-setup)
12. [Checklist khi viết code mới](#12-checklist-khi-viết-code-mới)

---

## 1. Tổng quan và Design Patterns

### 1.1 Tech Stack

| Thành phần    | Công nghệ                        | Vai trò                       |
| ------------- | -------------------------------- | ----------------------------- |
| Framework     | Django 4.2 + DRF 3.16            | Core API                      |
| Database      | PostgreSQL (Supabase)            | Lưu trữ chính                 |
| Cache         | Redis                            | Session cache, response cache |
| Auth          | Custom token (DB) + Supabase JWT | Xác thực                      |
| Thanh toán    | Stripe                           | Subscription Premium          |
| AI            | Google Gemini                    | Gợi ý bài hát                 |
| Music sources | YouTube (yt-dlp), Jamendo, NCT   | Nguồn nhạc                    |
| Deploy        | Docker + Gunicorn + Gevent       | Production server             |

### 1.2 Các Design Pattern được áp dụng

#### Pattern 1: Service Layer (Tách logic gọi API ngoài ra riêng)

```
views.py  →  services/youtube.py
          →  services/jamendo.py
          →  services/gemini_client.py
          →  services/stripe_service.py
```

**Tại sao:** View chỉ chịu trách nhiệm nhận request và trả response. Logic gọi YouTube, Stripe, Gemini được tách ra `services/` để:

- Dễ mock trong test (không cần gọi API thật)
- Dễ thay thế implementation (đổi YouTube library không ảnh hưởng view)
- Dễ tái sử dụng từ nhiều view

```python
# ĐÚNG — view gọi service
from services.youtube import extract_audio_url
result = extract_audio_url(video_id)

# SAI — view tự gọi yt-dlp trực tiếp
import yt_dlp
ydl = yt_dlp.YoutubeDL(...)
```

#### Pattern 2: Repository-like với Django ORM

Django ORM đóng vai trò Repository — tất cả query DB đi qua `Model.objects.*`. Project áp dụng quy tắc:

- Không viết raw SQL trừ khi cần PostgreSQL-specific feature (upsert `ON CONFLICT`)
- Tập trung query phức tạp vào các helper function (vd: `_db_search_results`, `_db_genre_results` trong `music/views.py`)

#### Pattern 3: DB-First với External Fallback

Chiến lược tìm kiếm nhất quán trong toàn project:

```
1. Tìm trong DB nội bộ  →  nhanh, không tốn API quota
       ↓ nếu rỗng
2. Gọi API ngoài (YouTube/Jamendo/NCT)  →  chậm hơn, tốn quota
       ↓ song song
3. Lưu kết quả API ngoài vào DB (background)  →  lần sau dùng DB
```

```python
# music/views.py — SearchView
db_results = _db_search_results(query, limit)
if db_results:
    return success(db_results)  # Fast path

# Slow path — gọi song song các nguồn bên ngoài
with ThreadPoolExecutor(max_workers=3) as ex:
    futures['youtube'] = ex.submit(search_youtube, query, limit)
    futures['jamendo'] = ex.submit(jamendo_search, query, limit)
```

#### Pattern 4: Version-Based Cache Invalidation

Thay vì track từng cache key để xóa, dùng version counter. Khi danh sách thay đổi, tăng version — tất cả cache key cũ chứa version cũ sẽ tự động miss mà không cần xóa từng cái:

```python
# Cache key nhúng version
f'history-page:{user_id}:{version}:{offset}:{limit}'

# Khi write → tăng version → key cũ không bao giờ được hit nữa
cache.incr(f'history-version:{user_id}')
```

#### Pattern 5: Fail-Safe External Calls

Khi gọi API ngoài (YouTube, Jamendo, Gemini, NCT), luôn bọc trong try/except và fallback về kết quả rỗng thay vì để lỗi nổi lên:

```python
# recommendations/views.py
try:
    suggestions = gemini_recommend(title, artist) or []
except Exception:
    logger.warning('Gemini recommend failed for "%s - %s"', title, artist, exc_info=True)
    suggestions = []  # Fallback: trả kết quả rỗng, không crash API
```

#### Pattern 6: Single Responsibility trong View

Mỗi view class chỉ xử lý một resource. Không nhồi nhiều logic khác nhau vào một view:

```python
class PlaylistListView(APIView):    # Chỉ list + create playlist
class PlaylistDetailView(APIView):  # Chỉ get + update + delete một playlist
class PlaylistSongManageView(APIView):  # Chỉ add/remove bài trong playlist
class PlaylistReorderView(APIView):     # Chỉ reorder bài
```

---

## 2. Docker — Image, Container, và Setup

### 2.1 Khái niệm cốt lõi

**Image** là bản thiết kế (blueprint) — giống như file `.exe` chưa chạy. Nó chứa:

- Hệ điều hành base (ở đây là `python:3.12-slim-bookworm` — Debian Bookworm, chỉ gồm phần tối thiểu)
- Tất cả dependencies đã cài
- Source code của app
- Cấu hình cách chạy

**Container** là instance đang chạy từ image — giống như một process được cô lập hoàn toàn. Nhiều container có thể chạy từ cùng một image.

```
Image (bản thiết kế)  →  docker build  →  docker run  →  Container (đang chạy)
```

### 2.2 Phân tích Dockerfile của project

```dockerfile
# Base image: Python 3.12 trên Debian Bookworm, bản slim (bỏ hầu hết package không cần)
FROM python:3.12-slim-bookworm

# Tắt .pyc files (giảm kích thước image) và unbuffered output (log xuất hiện ngay)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Thư mục làm việc trong container
WORKDIR /app

# Cài ffmpeg trước vì yt-dlp cần ffmpeg để xử lý audio
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*    # Xóa cache apt → giảm kích thước image

# Copy requirements TRƯỚC, sau đó pip install
# Kỹ thuật layer caching: nếu requirements.txt không đổi, Docker dùng cache layer
# thay vì chạy lại pip install (tiết kiệm thời gian build)
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy toàn bộ code (sau pip install để tận dụng cache tốt hơn)
COPY . .

# Tạo user non-root để chạy app (bảo mật: tránh chạy với quyền root)
RUN adduser --disabled-password --no-create-home appuser && \
    chown -R appuser:appuser /app

USER appuser   # Không bao giờ chạy app bằng root trong production

EXPOSE 8000    # Khai báo port (chỉ là documentation, không tự publish port ra ngoài)

ENTRYPOINT ["/app/entrypoint.sh"]   # Script chạy migrate rồi mới start server
```

### 2.3 Phân tích docker-compose.yml

```yaml
services:
  redis:
    image: redis:7-alpine # Dùng image có sẵn từ Docker Hub, bản alpine (nhẹ)
    restart: unless-stopped # Tự restart nếu crash, trừ khi bị stop thủ công
    ports:
      - "6379:6379" # host:container — port 6379 host → 6379 trong container
    volumes:
      - redis_data:/data # Persist data Redis (không mất khi restart container)
    healthcheck:
      test: ["CMD", "redis-cli", "ping"] # Kiểm tra Redis còn sống
      interval: 5s
      retries: 5

  api:
    build: . # Build image từ Dockerfile trong thư mục hiện tại
    ports:
      - "8001:8000" # Truy cập qua localhost:8001, map vào port 8000 container
    env_file:
      - ../.env # Đọc biến môi trường từ .env
    environment:
      - REDIS_URL=redis://redis:6379/0 # Dùng tên service "redis" thay vì localhost
    depends_on:
      redis:
        condition: service_healthy # Chờ Redis healthy mới start API
    volumes:
      - .:/app # Mount code vào container (live reload khi dev)
    command: >
      gunicorn config.wsgi:application
        --bind 0.0.0.0:8000
        --workers 3            # 3 worker process xử lý request song song
        --worker-class gevent  # Async I/O — hiệu quả khi nhiều request chờ I/O
        --timeout 120          # Request timeout 120s (YouTube download cần thời gian)
        --access-logfile -     # Log access ra stdout (để Docker thu thập)
        --error-logfile -      # Log error ra stderr

volumes:
  redis_data: # Named volume, Docker quản lý, persist giữa các lần restart
```

> **Lưu ý quan trọng:** Trong `docker-compose`, các service giao tiếp nhau qua **tên service** (không phải `localhost`). API kết nối Redis qua `redis://redis:6379/0` vì service Redis tên là `redis`. Đây là điểm hay nhầm khi debug.

### 2.4 entrypoint.sh — Script khởi động

```sh
#!/bin/sh
set -e          # Dừng ngay nếu có lệnh nào fail

python manage.py migrate --noinput        # Chạy migration trước khi start server
python manage.py collectstatic --noinput  # Thu thập static files

exec "$@"       # Chạy command được truyền vào (Gunicorn từ docker-compose)
```

`exec "$@"` đảm bảo Gunicorn là PID 1 trong container — quan trọng để SIGTERM (tín hiệu stop container) được xử lý đúng.

### 2.5 Các lệnh Docker thường dùng

```bash
# Build và start tất cả services
docker-compose up --build

# Chạy background
docker-compose up -d

# Xem logs của API service
docker-compose logs -f api

# Xem logs của Redis
docker-compose logs -f redis

# Chạy lệnh trong container đang chạy
docker-compose exec api python manage.py shell
docker-compose exec api python manage.py migrate

# Stop tất cả
docker-compose down

# Stop và xóa volumes (reset Redis data)
docker-compose down -v
```

### 2.6 Lý do chọn Gunicorn + Gevent

- **Gunicorn** là WSGI server production (không dùng `python manage.py runserver` vì không scale)
- **Gevent** là async I/O worker — khi một request đang chờ YouTube/Stripe trả về, worker có thể xử lý request khác thay vì bị block. Phù hợp với workload của Sonus (nhiều I/O: YouTube, Redis, DB)

---

## 3. JSON Response chuẩn

### 3.1 Chuẩn tham chiếu: JSend

Project theo biến thể của [JSend specification](https://github.com/omniti-labs/jsend) — một chuẩn đơn giản cho JSON API response. JSend định nghĩa 3 loại: `success`, `fail`, `error`. Project đơn giản hóa thành 2 loại (`success` / `error`) và thêm `code`.

### 3.2 Schema thành công

```json
{
  "status": "success",
  "code": 200,
  "message": "Play recorded",
  "data": {
    "count": 5
  }
}
```

| Field     | Kiểu        | Ý nghĩa                              |
| --------- | ----------- | ------------------------------------ |
| `status`  | `"success"` | Luôn là `"success"` khi thành công   |
| `code`    | integer     | HTTP status code (200, 201, 202)     |
| `message` | string      | Mô tả ngắn gọn, có thể để trống `""` |
| `data`    | any         | Payload — object, array, hoặc null   |

**204 No Content** — duy nhất không có body:

```python
return no_content()  # HTTP 204, không có JSON body
```

### 3.3 Schema lỗi

```json
{
  "status": "error",
  "code": 404,
  "message": "Playlist not found",
  "errors": null
}
```

**Khi có lỗi validation từng field (422):**

```json
{
  "status": "error",
  "code": 422,
  "message": "Validation failed",
  "errors": {
    "email": ["This field is required.", "Enter a valid email address."],
    "password": ["Ensure this field has at least 8 characters."]
  }
}
```

| Field     | Kiểu           | Ý nghĩa                                               |
| --------- | -------------- | ----------------------------------------------------- |
| `status`  | `"error"`      | Luôn là `"error"` khi lỗi                             |
| `code`    | integer        | HTTP status code                                      |
| `message` | string         | Mô tả lỗi cho developer (không hiển thị cho end-user) |
| `errors`  | object \| null | Chi tiết lỗi từng field, null nếu không có            |

### 3.4 Schema phân trang

Khi trả về danh sách với pagination:

```json
{
    "status": "success",
    "code": 200,
    "message": "",
    "data": {
        "items": [...],
        "pagination": {
            "current_page": 2,
            "last_page": 10,
            "per_page": 20,
            "total": 198
        }
    }
}
```

`last_page` và `total` là `null` khi client gửi `?return_total=false`.

### 3.5 Tất cả hàm trong core/responses.py

```python
# Thành công
success(data, message)     # 200 OK
created(data, message)     # 201 Created
accepted(data, message)    # 202 Accepted (async job)
no_content()               # 204 No Content

# Lỗi client
bad_request(message, errors)  # 400
unauthorized(message)          # 401
forbidden(message)             # 403
not_found(message)             # 404
method_not_allowed(message)    # 405
conflict(message, errors)      # 409
gone(message)                  # 410
unprocessable(message, errors) # 422
too_many_requests(message)     # 429

# Lỗi server
server_error(message)          # 500
bad_gateway(message)           # 502 — external service lỗi
service_unavailable(message)   # 503 — service chưa config
gateway_timeout(message)       # 504 — external service timeout
```

---

## 4. Error Handling — Nguyên tắc và Chuẩn

### 4.1 Kiến trúc xử lý lỗi

```
Request
   ↓
DRF Middleware
   ↓
View.dispatch()
   ↓
Serializer.is_valid(raise_exception=True)
   ↓  exception nếu invalid
custom_exception_handler()  ←  DRF gọi khi có exception
   ↓
Trả về JSON chuẩn
```

`core/exceptions.py` được đăng ký trong `settings.py`:

```python
REST_FRAMEWORK = {
    'EXCEPTION_HANDLER': 'core.exceptions.custom_exception_handler',
}
```

Điều này có nghĩa: **mọi exception từ DRF đều được bắt tự động** và chuyển thành JSON chuẩn. Intern không cần tự bắt `ValidationError`.

### 4.2 Luồng xử lý exception

```python
def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)  # DRF handler mặc định trước
    if response is None:
        return None  # DRF không handle được → Django xử lý → HTTP 500

    if isinstance(exc, ValidationError):
        # Serializer validation fail → 422 với chi tiết từng field
        return unprocessable(message='Validation failed', errors=response.data)

    # Các lỗi khác: map status code → response function
    handler = _STATUS_HANDLERS.get(response.status_code)
    if handler:
        return handler(message)
    return _error(message=message, code=response.status_code, errors=None)
```

### 4.3 Phân loại lỗi và cách xử lý

**Loại 1: Validation error — DRF tự bắt**

```python
# Không cần try/except, DRF + custom_exception_handler tự xử lý
serializer = LoginSerializer(data=request.data)
serializer.is_valid(raise_exception=True)  # Nếu fail → 422 tự động
```

**Loại 2: Business logic error — tự raise trong view**

```python
if not _is_premium_cached(str(request.user.id)):
    return forbidden('Charts are a Premium feature.')
```

**Loại 3: External service error — try/except với specific exception**

```python
try:
    result = extract_audio_url(video_id)
except YouTubeError as e:
    logger.warning('YouTube extract failed for video_id %s: %s', video_id, e)
    return bad_gateway(str(e))   # 502 — lỗi ở upstream, không phải lỗi của mình
```

**Loại 4: Unexpected error — catch Exception, log, trả 500**

```python
except Exception:
    logger.exception('Unexpected error in GenreTrackListView for genre "%s"', genre)
    return server_error()
```

### 4.4 Nguyên tắc khi chọn loại lỗi

| Tình huống                         | Status | Response function                      |
| ---------------------------------- | ------ | -------------------------------------- |
| Client gửi thiếu/sai param         | 400    | `bad_request()`                        |
| Validation serializer fail         | 422    | Tự động qua `custom_exception_handler` |
| Không có token / token hết hạn     | 401    | `unauthorized()`                       |
| Có token nhưng không đủ quyền      | 403    | `forbidden()`                          |
| Resource không tồn tại             | 404    | `not_found()`                          |
| Tạo duplicate (email đã dùng)      | 409    | `conflict()`                           |
| API ngoài (YouTube/Stripe) trả lỗi | 502    | `bad_gateway()`                        |
| Service chưa config (API key rỗng) | 503    | `service_unavailable()`                |
| Lỗi code không mong đợi            | 500    | `server_error()`                       |

### 4.5 Không nên làm

```python
# SAI — trả lỗi chung chung 400 cho mọi thứ
return bad_request('Something went wrong')

# SAI — để exception nổi lên không bắt (Django trả HTML 500)
result = extract_audio_url(video_id)

# SAI — nuốt exception im lặng (không log)
try:
    result = extract_audio_url(video_id)
except Exception:
    pass   # Developer không biết lỗi gì đang xảy ra

# SAI — expose internal error message cho client
except Exception as e:
    return server_error(str(e))   # Có thể lộ stack trace, DB schema
```

---

## 5. Logging — Xem ở đâu, Viết như thế nào

### 5.1 Log xuất hiện ở đâu?

**Development (runserver):** Thẳng ra terminal

```bash
python manage.py runserver
# Log xuất hiện trực tiếp trong terminal
```

**Docker (production):** Ra stdout/stderr của container

```bash
# Xem log realtime
docker-compose logs -f api

# Xem 100 dòng log cuối
docker-compose logs --tail=100 api

# Xem log kèm timestamp
docker-compose logs -f -t api
```

Gunicorn được cấu hình `--access-logfile - --error-logfile -` nghĩa là cả access log và error log đều ra stdout/stderr để Docker thu thập.

**Trong code:** Django sử dụng Python's built-in `logging` module. Cấu hình logging hiện tại trong project dùng `LOGGING` mặc định của Django (output ra console).

### 5.2 Khởi tạo logger đúng cách

```python
import logging

# Đặt ở đầu mỗi file, NGOÀI hàm/class
logger = logging.getLogger(__name__)
# __name__ = tên module đầy đủ, vd: "music.views", "accounts.authentication"
# Điều này cho phép filter log theo module trong production
```

### 5.3 Chọn log level đúng

| Level       | Khi nào dùng                           | Ví dụ trong project                         |
| ----------- | -------------------------------------- | ------------------------------------------- |
| `DEBUG`     | Chi tiết nội bộ, chỉ khi debug         | Không dùng trong views                      |
| `INFO`      | Sự kiện bình thường quan trọng         | `logger.info('User %s logged in', user.id)` |
| `WARNING`   | Vấn đề nhưng app vẫn hoạt động         | External API fail, cache miss quan trọng    |
| `ERROR`     | Lỗi nghiêm trọng, cần điều tra         | Unexpected exception với exc_info           |
| `EXCEPTION` | Trong except block, tự add stack trace | `logger.exception(...)`                     |

### 5.4 Format log message chuẩn

```python
# ĐÚNG — dùng % (lazy evaluation)
logger.warning('YouTube extract failed for video_id %s: %s', video_id, e)
logger.error('Search source %s failed for query "%s"', name, query, exc_info=True)

# SAI — f-string bị evaluate dù log level bị tắt (lãng phí CPU)
logger.warning(f'YouTube failed for {video_id}: {e}')
```

**Cấu trúc message tốt:**

- Bắt đầu bằng **hành động/location**: `'YouTube extract failed for'`, `'Gemini recommend failed for'`
- Đính kèm **context** (ID, query, giá trị liên quan): `%s`, không phải chỉ `'Something failed'`
- Thêm `exc_info=True` khi muốn stack trace đầy đủ (hoặc dùng `.exception()`)

```python
# Trong except block: dùng .exception() — tự thêm stack trace
try:
    lyric = fetch_and_store_lyrics(song_id)
except Exception:
    logger.exception('fetch_and_store_lyrics failed for song_id %s', song_id)
    return server_error('Failed to fetch lyrics')

# Khi không trong except block nhưng muốn stack trace
logger.error('Unexpected state in %s', __name__, exc_info=True)
```

### 5.5 Những gì KHÔNG được log

```python
# KHÔNG log credential, token, password
logger.info('User logged in with token %s', token)     # SAI
logger.debug('Password hash: %s', credential.password_hash)  # SAI

# KHÔNG log toàn bộ request.data (có thể chứa password)
logger.info('Request data: %s', request.data)           # SAI

# KHÔNG log PII (thông tin cá nhân) không cần thiết
logger.info('User email: %s logged in', user.email)    # Cân nhắc — email là PII
```

### 5.6 Thêm LOGGING config vào settings (nếu cần tùy chỉnh)

```python
# settings.py — thêm block này để có structured logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'music': {'handlers': ['console'], 'level': 'DEBUG', 'propagate': False},
    },
}
```

---

## 6. Serializer — Nguyên tắc và Quy chuẩn

### 6.1 Nguyên tắc cốt lõi: Fat Serializer, Thin View

View chỉ làm 3 việc: nhận request → gọi serializer → trả response. **Logic validation và business rule nằm trong serializer.**

```python
# THIN VIEW — đúng
class LoginView(APIView):
    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        return auth_response(serializer.validated_data['user'], request)

# FAT VIEW — sai (validation trong view)
class LoginView(APIView):
    def post(self, request):
        email = request.data.get('email')
        if not email:
            return bad_request('Email required')
        user = User.objects.filter(email=email).first()
        if not user:
            return bad_request('Invalid email or password')
        # ... tiếp tục validate trong view
```

### 6.2 Hai loại Serializer

**ModelSerializer** — khi output/input gắn trực tiếp với model:

```python
class SongSerializer(serializers.ModelSerializer):
    class Meta:
        model = Song
        fields = ['id', 'title', 'subtitle', 'image_url', 'audio_url', 'duration']
```

**Serializer** — khi validate input không gắn trực tiếp với model (form-like):

```python
class RecordPlaySerializer(serializers.Serializer):
    song_id = serializers.CharField(required=True)
    progress_percent = serializers.FloatField(default=100, min_value=0, max_value=100)
    title = serializers.CharField(required=False, allow_blank=True)
```

### 6.3 Validation ở ba tầng

**Tầng 1: Field-level** — validate từng field riêng lẻ

```python
def validate_email(self, value):
    email = value.lower()   # Normalize về lowercase
    if User.objects.filter(email=email).exists():
        raise serializers.ValidationError('Email is already registered')
    return email  # PHẢI return value (đã normalize)
```

**Tầng 2: Object-level** — validate liên quan giữa nhiều field

```python
def validate(self, attrs):
    user = User.objects.filter(email=attrs['email'].lower()).first()
    if not user or not user.credential.check_password(attrs['password']):
        raise serializers.ValidationError('Invalid email or password')
    attrs['user'] = user    # Thêm data vào validated_data để view dùng
    return attrs
```

**Tầng 3: View-level** — logic nghiệp vụ không thuộc về serializer (quota check, permission check)

```python
# Trong view sau khi serializer valid
if not _is_premium_cached(str(request.user.id)):
    current_count = LikedSong.objects.filter(user=request.user).count()
    if current_count >= FREE_FAVORITE_LIMIT:
        return forbidden('Favorite limit reached')
```

### 6.4 write_only và read_only

```python
class RegisterSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, min_length=8)
    # write_only=True → password KHÔNG BAO GIỜ xuất hiện trong response JSON
    # Quan trọng: tránh lộ password kể cả đã hash

class UserSerializer(serializers.ModelSerializer):
    class Meta:

        read_only_fields = ['id', 'email', 'is_premium', 'stats']
        # read_only → client có thể đọc nhưng không thể ghi qua PATCH
```

### 6.5 SerializerMethodField — Computed field

Dùng khi cần field được tính toán, không có sẵn trong model:

```python
class UserSerializer(serializers.ModelSerializer):
    is_premium = serializers.SerializerMethodField()
    stats = serializers.SerializerMethodField()

    def get_is_premium(self, obj):
        return self._subscription_status(obj).get('is_premium', False)

    def get_stats(self, obj):
        if not self.context.get('include_stats', False):
            return None   # Không tính nếu không yêu cầu — tiết kiệm query
        ...
```

### 6.6 source — Alias field name

```python
class LikedSongSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(source='liked_at', read_only=True)
    # DB có cột 'liked_at', API trả về tên 'created_at' để nhất quán
    # source='liked_at' → đọc từ model.liked_at nhưng serialize ra 'created_at'

class UserSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(source='full_name', required=False)
    # Model có field 'full_name', API dùng tên 'display_name' thân thiện hơn
```

### 6.7 Context — Truyền data từ view vào serializer

```python
# View truyền context
serializer = UserSerializer(
    request.user,
    context={'include_stats': True}
)

# Serializer đọc context
def get_stats(self, obj):
    if not self.context.get('include_stats', False):
        return None
```

### 6.8 Nested Serializer — Tránh N+1 query

```python
class PlayHistorySerializer(serializers.ModelSerializer):
    song = SongSerializer(read_only=True)   # Nested serializer

# View PHẢI dùng select_related để tránh N+1
qs = PlayHistory.objects.filter(user=request.user).select_related('song')
# Không có select_related: 1 query lấy history + N query lấy từng song
```

### 6.9 Partial update

```python
# PATCH — chỉ update các field được gửi lên
serializer = UserSerializer(request.user, data=request.data, partial=True)
serializer.is_valid(raise_exception=True)
serializer.save()
# partial=True: field không có trong request.data sẽ không bị thay đổi
```

---

## 7. Cache — Cấu trúc, Lưu, và Xóa

### 7.1 Cấu hình Redis

```python
# settings.py
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': config('REDIS_URL', default='redis://127.0.0.1:6379/0'),
    }
}

# Test settings — dùng LocMemCache để không cần Redis khi chạy test
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}
```

### 7.2 API Django Cache

```python
from django.core.cache import cache

# Lưu cache (timeout tính bằng giây, None = không hết hạn)
cache.set('my-key', value, timeout=300)

# Đọc cache (trả về None nếu miss)
value = cache.get('my-key')

# Đọc với default
value = cache.get('my-key', default=[])

# Xóa một key
cache.delete('my-key')

# Tăng counter (atomic, thread-safe)
cache.incr('counter-key')        # Tăng 1
cache.incr('counter-key', delta=5)  # Tăng 5
# Nếu key chưa tồn tại → raise ValueError → cần handle:
try:
    cache.incr(key)
except ValueError:
    cache.set(key, 2, timeout=None)
```

### 7.3 Taxonomy các loại cache trong project

**Loại A — Response cache (cache nguyên response data)**

| Cache key pattern         | TTL     | Xóa khi nào                     |
| ------------------------- | ------- | ------------------------------- |
| `search:v5:{hash}`        | 5 phút  | Không cần xóa (expire tự nhiên) |
| `home_feed:{tier}:v4`     | 30 phút | Không cần xóa                   |
| `chart:v2:{hash}`         | 30 phút | Không cần xóa                   |
| `genre:v2:{hash}`         | 30 phút | Không cần xóa                   |
| `related:v2:{hash}`       | 30 phút | Không cần xóa                   |
| `recommendations:v2:{id}` | 1 giờ   | Không cần xóa                   |
| `resolve:v2:{hash}`       | 1 giờ   | Không cần xóa                   |

**Loại B — User list cache (phân trang, thay đổi khi user thêm/xóa)**

| Cache key pattern                               | TTL     | Xóa khi nào                      |
| ----------------------------------------------- | ------- | -------------------------------- |
| `history-page:v1:{user}:{ver}:{off}:{lim}`      | 60 giây | Version bump khi ghi play        |
| `favorites-page:v1:{user}:{ver}:{off}:{lim}`    | 60 giây | Version bump khi toggle favorite |
| `downloads-page:v1:{user}:{ver}:{off}:{lim}`    | 60 giây | Version bump khi download        |
| `playlists-page:{user}:{ver}:{off}:{lim}`       | 60 giây | Version bump khi CRUD playlist   |
| `playlist-detail:{user}:{id}:{ver}:{off}:{lim}` | 60 giây | Version bump khi add/remove song |

**Loại C — Metadata cache (count, stats, subscription)**

| Cache key pattern           | TTL      | Xóa khi nào                              |
| --------------------------- | -------- | ---------------------------------------- |
| `user-premium:{user_id}`    | 60 giây  | Sau khi subscription thay đổi            |
| `user-stats:{user_id}`      | 60 giây  | Sau khi nghe/yêu thích/playlist thay đổi |
| `history-count:{user_id}`   | 30 giây  | Sau khi ghi/xóa play                     |
| `favorites-count:{user_id}` | 30 giây  | Sau khi toggle favorite                  |
| `downloads-count:{user_id}` | 30 giây  | Sau khi download/xóa                     |
| `playlists-count:{user_id}` | 30 giây  | Sau khi tạo/xóa playlist                 |
| `auth-session:{token_hash}` | 120 giây | Sau khi logout (revoke)                  |

**Loại D — Version counter (invalidation control)**

| Cache key pattern              | TTL                  | Xóa khi nào         |
| ------------------------------ | -------------------- | ------------------- |
| `history-version:{user_id}`    | Không hết hạn (None) | Không xóa, chỉ incr |
| `favorites-version:{user_id}`  | Không hết hạn        | Không xóa, chỉ incr |
| `downloads-version:{user_id}`  | Không hết hạn        | Không xóa, chỉ incr |
| `playlists-version:{user_id}`  | Không hết hạn        | Không xóa, chỉ incr |
| `playlist-detail-version:{pk}` | Không hết hạn        | Không xóa, chỉ incr |

### 7.4 Tạo cache key an toàn

Vấn đề với cache key thông thường:

```python
# SAI — query có thể chứa ký tự đặc biệt, quá dài
key = f'search:{query}:{limit}'   # 'search:sơn tùng mtp official mv:10' → lỗi Redis
```

Giải pháp: hash tất cả thành SHA-256:

```python
def _cache_key(prefix: str, *parts) -> str:
    raw = '|'.join(str(part) for part in parts)
    digest = hashlib.sha256(raw.encode('utf-8')).hexdigest()
    return f'{prefix}:{digest}'

# Dùng
cache_key = _cache_key('search:v5', query.strip().lower(), limit, sources, premium)
# → 'search:v5:a8f4c2d1e3b5...' (luôn 64 ký tự hex)
```

### 7.5 Version bump pattern chi tiết

```python
# Bước 1 — Đọc version hiện tại
def _user_list_version(user_id: str, list_name: str) -> int:
    return cache.get(f'{list_name}-version:{user_id}') or 1

# Bước 2 — Nhúng version vào cache key khi đọc
cache_key = _cache_key(
    'history-page:v1',
    request.user.id,
    _user_list_version(str(request.user.id), 'history'),  # ← version
    offset, limit,
)

# Bước 3 — Tăng version khi write (invalidate tất cả page cũ)
def _bump_user_list_version(user_id: str, list_name: str):
    key = f'{list_name}-version:{user_id}'
    try:
        cache.incr(key)        # 1 → 2 → 3 → ...
    except ValueError:
        cache.set(key, 2, timeout=None)   # Khởi tạo nếu chưa có
```

**Tại sao không xóa từng cache page?**

- Khó track hết tất cả page offset đang được cache
- Race condition: có thể miss một page nào đó
- Version bump đơn giản hơn: tăng 1 số, mọi key cũ tự trở nên stale

### 7.6 Cache trong serializer (memoization trong một request)

```python
# accounts/serializers.py — UserSerializer
def _subscription_status(self, obj):
    # Cache trong context để is_premium và premium_until chỉ gọi Stripe 1 lần
    if 'subscription_status' in self.context:
        return self.context['subscription_status']
    result = get_subscription_status(str(obj.id))
    self.context['subscription_status'] = result   # Lưu vào context
    return result
```

---

## 8. Authentication — Token, Bảo mật, Vòng đời

### 8.1 Kiến trúc tổng thể

```
Client                              Server
  │                                    │
  │  POST /api/auth/login/             │
  │  {email, password}                 │
  ├──────────────────────────────────→ │
  │                                    │  Verify password
  │                                    │  Tạo UserSession
  │                                    │  token = secrets.token_urlsafe(48)
  │                                    │  Lưu DB: token_hash = SHA256(token)
  │  {token: "raw_token", expires_at}  │
  ←─────────────────────────────────── │
  │                                    │
  │  GET /api/me/                       │
  │  Authorization: Bearer raw_token   │
  ├──────────────────────────────────→ │
  │                                    │  hash token → tìm trong Redis
  │                                    │  (nếu miss) tìm trong DB
  │                                    │  Kiểm tra is_valid
  │  {user data}                       │
  ←─────────────────────────────────── │
```

### 8.2 Token được lưu trữ như thế nào?

**Server lưu trong DB (bảng `user_sessions`):**

```python
token_hash = models.CharField(max_length=64, unique=True)
# SHA-256 hex digest (64 ký tự), KHÔNG lưu token gốc
```

**Tại sao hash token trước khi lưu?**

- Nếu DB bị breach, attacker có `token_hash` nhưng không thể reverse lại `token` gốc
- SHA-256 là one-way hash — không có cách nào tính ngược
- Khác với password: token không cần salt vì đã đủ entropy (48 bytes = 64+ bit entropy)

**Server cũng cache trong Redis:**

```python
cache_key = f'auth-session:{token_hash}'
cache.set(cache_key, session, timeout=120)  # Cache 120 giây
```

**Client lưu ở đâu?** — Project không quy định (đó là việc của Flutter app), nhưng best practice:

- Mobile: Secure Storage (iOS Keychain / Android Keystore)
- Web: httpOnly cookie hoặc localStorage (cân nhắc XSS risk)

### 8.3 Vòng đời của token

```
Tạo token khi:     Login, Register, Supabase OAuth exchange
TTL:               30 ngày (AUTH_SESSION_TTL_DAYS từ .env)
Revoke token khi:  Logout (gọi POST /api/auth/logout/)
Xóa cache khi:     Logout
Token hết hạn:     expires_at < now() → is_valid = False
Kiểm tra hợp lệ:   revoked_at IS NULL AND expires_at > NOW()
```

```python
# accounts/models.py
@property
def is_valid(self):
    return self.revoked_at is None and self.expires_at > timezone.now()
```

### 8.4 Multi-device: Nhiều session song song

Mỗi lần login tạo **một session mới độc lập**. User có thể đăng nhập từ iPhone, iPad, và web cùng lúc — mỗi thiết bị có token riêng. Logout một thiết bị không ảnh hưởng thiết bị khác:

```python
class UserSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sessions')
    device_id = models.CharField(max_length=255, blank=True)
    device_name = models.CharField(max_length=255, blank=True)
    # Một user → nhiều session (nhiều thiết bị)
```

### 8.5 Cơ chế revoke (logout)

```python
# accounts/views.py — LogoutView
def post(self, request):
    request.auth_session.revoke()             # Đánh dấu revoked_at = now()
    cache_key = getattr(request, 'auth_session_cache_key', None)
    if cache_key:
        cache.delete(cache_key)               # Xóa khỏi Redis ngay lập tức
    return no_content()
```

```python
# accounts/models.py — UserSession.revoke()
def revoke(self):
    self.revoked_at = timezone.now()
    self.save(update_fields=['revoked_at'])    # Chỉ update một field, không overwrite toàn bộ
```

**Tại sao phải xóa cache sau revoke?**

- Nếu không xóa, trong 120 giây cache TTL, token bị revoke vẫn có thể authenticate
- Xóa cache ngay sau revoke đảm bảo token không dùng được từ thời điểm logout

### 8.6 Hai flow OAuth vs Internal

**Internal (Email+Password):**

```
RegisterSerializer.create()
    → User.objects.create()
    → UserCredential.set_password(raw)  # PBKDF2+salt hash
    → UserSession.create_for_user()
```

**Supabase OAuth:**

```
Client đăng nhập Google qua Supabase SDK
    → Nhận Supabase JWT
    → Gửi JWT lên /api/auth/supabase-exchange/
    → verify_supabase_jwt(token)  # Verify HS256 + audience + issuer
    → User.objects.get_or_create(email=...)  # Tự tạo account lần đầu
    → UserSession.create_for_user()
```

### 8.7 Bảo mật bổ sung

**IP và User-Agent tracking:**

```python
session = UserSession(
    ip_address=cls._client_ip(request),     # Lưu IP để audit
    user_agent=request.META.get('HTTP_USER_AGENT', ''),  # Lưu browser/app info
)
```

**X-Forwarded-For handling (chạy sau nginx/load balancer):**

```python
forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
if forwarded_for:
    return forwarded_for.split(',')[0].strip()  # IP đầu tiên = IP client thực
```

**Thông báo lỗi generic khi login fail:**

```python
# accounts/serializers.py — LoginSerializer
raise serializers.ValidationError('Invalid email or password')
# KHÔNG nói 'Email không tồn tại' hay 'Sai mật khẩu' riêng lẻ
# → Ngăn attacker enumerate user (biết email nào tồn tại)
```

---

## 9. Authorization — Phân quyền Free/Premium

### 9.1 Cơ chế kiểm tra Premium

```python
# core/permissions.py
def is_premium(user_id):
    sub = Subscription.objects.filter(
        user_id=user_id,
        status__in=['active', 'trialing'],  # 'canceled', 'past_due' = không Premium
    ).order_by('-current_period_end').first()

    return sub is not None and (
        sub.current_period_end is None          # Subscription vĩnh viễn
        or sub.current_period_end > timezone.now()  # Còn trong kỳ thanh toán
    )
```

**Quan trọng:** `cancel_at_period_end=True` nghĩa là user đã hủy nhưng **vẫn còn quyền** đến hết kỳ (`current_period_end`). `is_premium()` vẫn trả True trong trường hợp này vì check `current_period_end > now()`.

### 9.2 Cache trạng thái Premium

```python
def _is_premium_cached(user_id: str) -> bool:
    key = f'user-premium:{user_id}'
    cached = cache.get(key)
    if cached is not None:
        return cached
    premium = is_premium(user_id)
    cache.set(key, premium, timeout=60)  # Cache 60 giây
    return premium
```

**Trade-off:** Sau khi upgrade/downgrade, có độ trễ tối đa 60 giây trước khi cache expire và status cập nhật đúng. Chấp nhận được vì Stripe webhook thường cũng có độ trễ vài giây.

### 9.3 Bảng giới hạn Free tier

```python
# core/permissions.py — Nguồn sự thật duy nhất cho tất cả limits
FREE_DOWNLOAD_LIMIT = 20     # Bài
FREE_PLAYLIST_LIMIT = 5      # Playlist
FREE_FAVORITE_LIMIT = 100    # Bài yêu thích
FREE_HISTORY_DAYS = 7        # Ngày xem lịch sử
FREE_SEARCH_LIMIT = 10       # Kết quả mỗi lần tìm
```

**Nguyên tắc:** Tất cả limit **phải** import từ đây, không hardcode trong view. Khi muốn thay đổi limit, chỉ sửa một chỗ.

### 9.4 Các tính năng Premium

| Tính năng          | Free            | Premium                       |
| ------------------ | --------------- | ----------------------------- |
| Tìm kiếm           | 10 kết quả      | Không giới hạn                |
| Playlist           | Tối đa 5        | Không giới hạn                |
| Yêu thích          | Tối đa 100      | Không giới hạn                |
| Download offline   | Tối đa 20       | Không giới hạn                |
| Lịch sử nghe       | 7 ngày gần nhất | Toàn bộ                       |
| Charts theo region | Không có        | Có (V-Pop, US-UK, K-Pop, ...) |

### 9.5 IsPremiumUser Permission Class

Dùng khi cần **block hoàn toàn** endpoint cho Free user (thay vì chỉ giới hạn số lượng):

```python
from core.permissions import IsPremiumUser

class ExportPlaylistView(APIView):
    permission_classes = [IsAuthenticated, IsPremiumUser]
    # → Tự động trả 403 nếu không phải Premium
    # → Không cần check thủ công trong view
```

---

## 10. Database — Patterns và Best Practices

### 10.1 Managed vs Unmanaged Model

| Model                      | managed | Bảng tạo bởi           |
| -------------------------- | ------- | ---------------------- |
| `User`                     | False   | Supabase Auth          |
| `Song`                     | False   | Migration cũ / crawler |
| `PlayHistory`              | False   | Migration cũ           |
| `LikedSong`                | False   | Migration cũ           |
| `Lyric`                    | True    | Django migration       |
| `Playlist`, `PlaylistSong` | False   | Migration cũ           |
| `Subscription`             | False   | Stripe webhook         |
| `UserSession`              | True    | Django migration       |
| `UserCredential`           | True    | Django migration       |
| `DownloadedSong`           | True    | Django migration       |

**Khi thêm model mới:** Nếu bảng đã tồn tại trong DB → `managed = False`. Nếu tạo bảng mới → `managed = True` (mặc định) + `makemigrations`.

### 10.2 Index Strategy

```python
# accounts/models.py — UserSession
class Meta:
    indexes = [
        models.Index(fields=['token_hash']),        # Lookup nhanh khi authenticate
        models.Index(fields=['user', 'revoked_at']),  # Tìm active session của user
    ]
```

**Khi nào thêm index:**

- Field thường xuất hiện trong `filter()` hoặc `order_by()`
- FK field (user_id, song_id) thường cần index
- Field có `unique=True` đã tự có index (unique constraint = index)

**Cẩn thận:** Index tốn disk và làm chậm write. Chỉ thêm khi có evidence cần (slow query log, EXPLAIN ANALYZE).

### 10.3 PostgreSQL UPSERT

```python
# music/views.py — RecordPlayView
if connection.vendor == 'postgresql':
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
    # Fallback ORM cho SQLite (test environment)
    ...
```

`ON CONFLICT` đảm bảo atomicity — không có race condition kể cả 100 request đồng thời ghi cùng một cặp `(user_id, song_id)`.

### 10.4 Transaction cho thao tác nhiều bước

```python
# playlists/views.py — PlaylistReorderView
from django.db import transaction

with transaction.atomic():
    playlist_songs = list(PlaylistSong.objects.filter(playlist_id=pk, song_id__in=song_ids))
    for playlist_song in playlist_songs:
        playlist_song.position = position_by_song[playlist_song.song_id]
    PlaylistSong.objects.bulk_update(playlist_songs, ['position'])
# Nếu bất kỳ bước nào fail → rollback toàn bộ
```

### 10.5 select_related vs prefetch_related

```python
# select_related — cho ForeignKey và OneToOne (SQL JOIN)
PlaylistSong.objects.filter(...).select_related('song')
# → 1 query: SELECT playlist_songs.*, songs.* FROM ... JOIN songs

# prefetch_related — cho ManyToMany hoặc reverse FK (2 query riêng)
Playlist.objects.filter(...).prefetch_related('playlistsong_set__song')
# → Query 1: SELECT playlists
# → Query 2: SELECT playlist_songs JOIN songs WHERE playlist_id IN (...)
```

---

## 11. Testing Setup

### 11.1 Cấu hình test

```ini
# pytest.ini
[pytest]
DJANGO_SETTINGS_MODULE = config.test_settings
```

```python
# config/test_settings.py
from .settings import *

# SQLite in-memory thay vì PostgreSQL — nhanh hơn, không cần DB thật
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}

# LocMemCache thay vì Redis — không cần Redis khi test
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}

# MD5 thay vì PBKDF2 — hash password nhanh hơn trong test
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
```

### 11.2 Fixtures sẵn có

```python
# conftest.py — dùng ngay không cần import
user               # User(email='test@example.com')
user_session       # (token, session) — session active
auth_headers       # {'HTTP_AUTHORIZATION': 'Bearer <token>'}
api_client         # APIClient chưa auth
auth_client        # APIClient đã auth + client.user
song               # Song(id='test_song_1', source='youtube')
another_song       # Song(id='test_song_2')
playlist           # Playlist của user
premium_subscription  # Subscription(status='active', ...)
auth_premium_client   # APIClient với Premium user
```

### 11.3 Viết test mẫu

```python
import pytest

@pytest.mark.django_db
class TestFavoriteToggle:

    def test_add_favorite(self, auth_client, song):
        response = auth_client.post(f'/api/favorites/{song.id}/', {'liked': True})
        assert response.status_code == 200
        assert response.data['data']['liked'] is True

    def test_free_tier_limit(self, auth_client, db):
        from music.models import LikedSong
        from core.permissions import FREE_FAVORITE_LIMIT
        # Tạo đủ bài yêu thích để đạt giới hạn
        for i in range(FREE_FAVORITE_LIMIT):
            Song.objects.get_or_create(id=f'song_{i}', defaults={'source': 'youtube'})
            LikedSong.objects.get_or_create(user=auth_client.user, song_id=f'song_{i}',
                                             defaults={'liked_at': timezone.now()})
        # Thêm một bài nữa → phải bị 403
        new_song = Song.objects.create(id='overflow_song', source='youtube')
        response = auth_client.post(f'/api/favorites/{new_song.id}/', {'liked': True})
        assert response.status_code == 403

    def test_premium_no_limit(self, auth_premium_client, song):
        response = auth_premium_client.post(f'/api/favorites/{song.id}/', {'liked': True})
        assert response.status_code == 200
```

### 11.4 Mock external services

```python
from unittest.mock import patch

@pytest.mark.django_db
def test_search_youtube_fallback(auth_client):
    with patch('services.youtube.search_youtube') as mock_yt:
        mock_yt.return_value = [{'id': 'yt123', 'title': 'Test', 'subtitle': 'Artist'}]
        response = auth_client.get('/api/search/?q=test')
    assert response.status_code == 200
    mock_yt.assert_called_once_with('test', 10)
```

---

## 12. Checklist khi viết code mới

### Khi viết View mới

- [ ] `logger = logging.getLogger(__name__)` ở đầu file
- [ ] Khai báo `permission_classes = [IsAuthenticated]` (hoặc `[AllowAny]` nếu public)
- [ ] Validate input bằng serializer với `is_valid(raise_exception=True)`
- [ ] Trả về response dùng `core/responses.py` — không `Response({...})` trực tiếp
- [ ] External API failures: `logger.warning()` + `return bad_gateway()`
- [ ] Unexpected exceptions: `logger.exception()` + `return server_error()`
- [ ] Đọc nhiều → thêm cache; Viết → xóa/bump cache liên quan
- [ ] Dùng `select_related()` khi serializer nested
- [ ] Thêm test: happy path + error case + limit check (nếu có quota)

### Khi viết Model mới

- [ ] Bảng đã có trong DB? → thêm `managed = False` + `db_table`
- [ ] Bảng mới hoàn toàn? → `makemigrations` + `migrate`
- [ ] Thêm index cho field filter/sort thường dùng
- [ ] Thêm model vào `_UNMANAGED_MODELS` trong `conftest.py` nếu `managed=False`

### Khi thêm feature có giới hạn Free/Premium

- [ ] Thêm constant giới hạn vào `core/permissions.py`
- [ ] Import constant từ đó, không hardcode trong view
- [ ] Kiểm tra `_is_premium_cached()`, không gọi `is_premium()` trực tiếp
- [ ] Return `forbidden()` khi vượt giới hạn với message rõ ràng

### Bảng lỗi phổ biến

| Lỗi                                     | Hậu quả                           | Cách tránh                                |
| --------------------------------------- | --------------------------------- | ----------------------------------------- |
| Hardcode API key                        | Security breach                   | Dùng `config('KEY')` từ `.env`            |
| `Response({...})` trực tiếp             | JSON không chuẩn, client bị lỗi   | Dùng `success()`, `bad_request()`,...     |
| Không log external API fail             | Debug mù khi production lỗi       | `logger.warning()` trong except           |
| Không `select_related()`                | N+1 query, DB quá tải             | Thêm khi serializer nested                |
| `get_or_create()` không dùng khi upsert | Race condition                    | Dùng `get_or_create()` hoặc `ON CONFLICT` |
| Quên `_bump_version()` sau write        | Cache stale, user thấy dữ liệu cũ | Sau mọi write operation                   |
| Validate trong view thay vì serializer  | Code lặp, khó test                | Chuyển logic vào serializer               |
| Log `request.data` nguyên xi            | Lộ password                       | Không bao giờ log raw request data        |
| Hardcode limit (vd `20`) trong view     | Khi đổi limit phải sửa nhiều chỗ  | Import từ `core/permissions.py`           |
| `makemigrations` cho unmanaged model    | Migration rỗng, confusing         | Kiểm tra `managed` trước khi migrate      |
