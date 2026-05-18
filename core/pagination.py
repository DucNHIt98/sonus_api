"""
Pagination chuẩn cho các endpoint trả về danh sách.

Dựa trên pattern offset/limit đang dùng khắp codebase, hàm paginate()
tính toán metadata trang (current_page, last_page, per_page, total)
từ offset và limit rồi gói kết quả vào schema chuẩn.

Schema phân trang:
    {
        "items": [...],
        "pagination": {
            "current_page": 1,
            "last_page": 5,
            "per_page": 20,
            "total": 100
        }
    }

Dùng trong response:
    return success(paginate(items, offset, limit, total))
    # → {status, code, message, data: {items, pagination}}
"""

import math
from typing import Any


def paginate(
    items: list[Any],
    offset: int,
    limit: int,
    total: int | None = None,
) -> dict:
    """
    Gói danh sách items đã slice vào schema phân trang chuẩn.

    Hàm này KHÔNG tự slice queryset — view phải truyền items đã được
    cắt đúng offset/limit để tránh query lại DB.

    Args:
        items: Danh sách items đã slice (list hoặc serialized data).
        offset: Vị trí bắt đầu (0-based).
        limit: Số items mỗi trang.
        total: Tổng số records (None nếu client không yêu cầu return_total).

    Returns:
        dict với keys 'items' và 'pagination'.

    Example:
        qs = PlayHistory.objects.filter(user=user).order_by('-last_played')
        data = PlayHistorySerializer(qs[offset:offset + limit], many=True).data
        return success(paginate(data, offset, limit, total=qs.count()))
    """
    # current_page tính từ 1 (page 1 = offset 0..limit-1)
    current_page = (offset // limit) + 1 if limit > 0 else 1

    # last_page chỉ tính được khi biết total; None khi client tắt return_total
    last_page = math.ceil(total / limit) if (total is not None and limit > 0) else None

    return {
        'items': list(items),
        'pagination': {
            'current_page': current_page,
            'last_page': last_page,
            'per_page': limit,
            'total': total,
        },
    }


def parse_offset_limit(request, default_limit: int = 20) -> tuple[int, int]:
    """
    Đọc và validate offset/limit từ query params.
    Đặt cận dưới 0 cho offset, cận dưới 1 cho limit để tránh lỗi slice.

    Example:
        offset, limit = parse_offset_limit(request)
        offset, limit = parse_offset_limit(request, default_limit=50)
    """
    try:
        offset = max(0, int(request.query_params.get('offset', 0)))
    except (TypeError, ValueError):
        offset = 0
    try:
        limit = max(1, int(request.query_params.get('limit', default_limit)))
    except (TypeError, ValueError):
        limit = default_limit
    return offset, limit
