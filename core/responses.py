"""
Bộ response chuẩn cho toàn bộ API.

Mọi view nên dùng các hàm trong module này thay vì gọi
Response({...}) trực tiếp để đảm bảo JSON schema thống nhất.

Schema thành công:
    {
        "status": "success",
        "code": 200,
        "message": "...",
        "data": <any>
    }

Schema lỗi:
    {
        "status": "error",
        "code": 400,
        "message": "...",
        "errors": <object | array | null>
    }
"""

from rest_framework import status as http_status
from rest_framework.response import Response


# ---------------------------------------------------------------------------
# Helpers nội bộ
# ---------------------------------------------------------------------------

def _success(data, message: str, code: int) -> Response:
    return Response(
        {'status': 'success', 'code': code, 'message': message, 'data': data},
        status=code,
    )


def _error(message: str, code: int, errors) -> Response:
    return Response(
        {'status': 'error', 'code': code, 'message': message, 'errors': errors},
        status=code,
    )


# ---------------------------------------------------------------------------
# 2xx — Thành công
# ---------------------------------------------------------------------------

def success(data=None, message: str = '') -> Response:
    """200 OK — trả về dữ liệu thành công."""
    return _success(data, message, http_status.HTTP_200_OK)


def created(data=None, message: str = '') -> Response:
    """201 Created — tạo mới resource thành công (POST)."""
    return _success(data, message, http_status.HTTP_201_CREATED)


def accepted(data=None, message: str = '') -> Response:
    """202 Accepted — request đã nhận nhưng xử lý bất đồng bộ (job queue, webhook)."""
    return _success(data, message, http_status.HTTP_202_ACCEPTED)


def no_content() -> Response:
    """204 No Content — thành công nhưng không có body (DELETE, logout)."""
    return Response(status=http_status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# 4xx — Lỗi phía client
# ---------------------------------------------------------------------------

def bad_request(message: str = 'Bad request', errors=None) -> Response:
    """400 Bad Request — request sai cú pháp, thiếu field, hoặc giá trị không hợp lệ."""
    return _error(message, http_status.HTTP_400_BAD_REQUEST, errors)


def unauthorized(message: str = 'Authentication required') -> Response:
    """401 Unauthorized — chưa đăng nhập hoặc token không hợp lệ/hết hạn."""
    return _error(message, http_status.HTTP_401_UNAUTHORIZED, None)


def forbidden(message: str = 'Permission denied') -> Response:
    """403 Forbidden — đã xác thực nhưng không có quyền thực hiện hành động này."""
    return _error(message, http_status.HTTP_403_FORBIDDEN, None)


def not_found(message: str = 'Not found') -> Response:
    """404 Not Found — resource không tồn tại hoặc không thuộc về user này."""
    return _error(message, http_status.HTTP_404_NOT_FOUND, None)


def method_not_allowed(message: str = 'Method not allowed') -> Response:
    """405 Method Not Allowed — HTTP method không được hỗ trợ trên endpoint này."""
    return _error(message, http_status.HTTP_405_METHOD_NOT_ALLOWED, None)


def conflict(message: str = 'Conflict', errors=None) -> Response:
    """409 Conflict — resource đã tồn tại (duplicate email, song đã trong playlist, ...)."""
    return _error(message, http_status.HTTP_409_CONFLICT, errors)


def gone(message: str = 'Resource no longer available') -> Response:
    """410 Gone — resource đã bị xóa vĩnh viễn (khác 404: biết chắc từng tồn tại)."""
    return _error(message, http_status.HTTP_410_GONE, None)


def unprocessable(message: str = 'Validation failed', errors=None) -> Response:
    """
    422 Unprocessable Entity — dữ liệu đúng cú pháp nhưng không pass validation nghiệp vụ.
    Dùng thay cho 400 khi lỗi cụ thể từng field (serializer.errors).
    """
    return _error(message, http_status.HTTP_422_UNPROCESSABLE_ENTITY, errors)


def too_many_requests(message: str = 'Too many requests, please slow down') -> Response:
    """429 Too Many Requests — bị rate limit."""
    return _error(message, http_status.HTTP_429_TOO_MANY_REQUESTS, None)


# ---------------------------------------------------------------------------
# 5xx — Lỗi phía server
# ---------------------------------------------------------------------------

def server_error(message: str = 'Internal server error') -> Response:
    """500 Internal Server Error — lỗi không mong đợi phía server."""
    return _error(message, http_status.HTTP_500_INTERNAL_SERVER_ERROR, None)


def bad_gateway(message: str = 'Upstream service error') -> Response:
    """502 Bad Gateway — service ngoài (YouTube, Stripe, Gemini, ...) trả về lỗi."""
    return _error(message, http_status.HTTP_502_BAD_GATEWAY, None)


def service_unavailable(message: str = 'Service temporarily unavailable') -> Response:
    """503 Service Unavailable — service chưa cấu hình hoặc đang bảo trì (Stripe not configured, ...)."""
    return _error(message, http_status.HTTP_503_SERVICE_UNAVAILABLE, None)


def gateway_timeout(message: str = 'Upstream service timed out') -> Response:
    """504 Gateway Timeout — service ngoài không phản hồi kịp thời."""
    return _error(message, http_status.HTTP_504_GATEWAY_TIMEOUT, None)
