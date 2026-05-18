"""
Custom exception handler cho DRF.

Khi DRF bắt exception (ValidationError, AuthenticationFailed, PermissionDenied, ...),
nó gọi hàm này thay vì dùng handler mặc định. Kết quả là mọi lỗi đều trả về
cùng schema chuẩn như core.responses.error().

Cấu hình trong settings.py:
    REST_FRAMEWORK = {
        ...
        'EXCEPTION_HANDLER': 'core.exceptions.custom_exception_handler',
    }

Schema lỗi chuẩn:
    {
        "status": "error",
        "code": 422,
        "message": "Validation failed",
        "errors": {
            "email": ["This field is required."],
            "password": ["Ensure this field has at least 8 characters."]
        }
    }
"""

from rest_framework import status as http_status
from rest_framework.exceptions import ValidationError
from rest_framework.views import exception_handler

from .responses import (
    bad_request,
    unauthorized,
    forbidden,
    not_found,
    method_not_allowed,
    unprocessable,
    server_error,
    _error,
)

# Map HTTP status code → hàm response chuẩn tương ứng
_STATUS_HANDLERS = {
    http_status.HTTP_400_BAD_REQUEST: bad_request,
    http_status.HTTP_401_UNAUTHORIZED: unauthorized,
    http_status.HTTP_403_FORBIDDEN: forbidden,
    http_status.HTTP_404_NOT_FOUND: not_found,
    http_status.HTTP_405_METHOD_NOT_ALLOWED: method_not_allowed,
    http_status.HTTP_422_UNPROCESSABLE_ENTITY: unprocessable,
    http_status.HTTP_500_INTERNAL_SERVER_ERROR: server_error,
}


def custom_exception_handler(exc, context):
    """
    Bọc tất cả DRF exception vào schema error chuẩn.

    Flow:
      1. Gọi DRF default handler trước để lấy response gốc.
      2. Nếu DRF không xử lý được (unhandled server error) → trả None,
         Django sẽ xử lý thành 500.
      3. Với ValidationError: dùng unprocessable() với errors dict chi tiết.
      4. Với các lỗi khác: dùng hàm tương ứng theo status code,
         fallback về _error() generic cho các code không có trong map.
    """
    response = exception_handler(exc, context)
    if response is None:
        # Unhandled exception — để Django 500 middleware xử lý
        return None

    if isinstance(exc, ValidationError):
        # ValidationError có thể có nhiều field → đưa toàn bộ vào errors
        return unprocessable(message='Validation failed', errors=response.data)

    # Lấy message từ 'detail' (chuẩn DRF) hoặc fallback về str(exc)
    if isinstance(response.data, dict):
        detail = response.data.get('detail', '')
        message = str(detail) if detail else str(exc)
    else:
        message = str(response.data)

    # Dùng hàm chuẩn nếu có trong map, fallback về _error generic
    handler = _STATUS_HANDLERS.get(response.status_code)
    if handler:
        return handler(message)
    return _error(message=message, code=response.status_code, errors=None)
