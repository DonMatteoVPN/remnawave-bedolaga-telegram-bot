from math import ceil
from typing import Any, Generic, TypeVar, List


T = TypeVar('T')


class PaginationResult(Generic[T]):
    """Результат пагинации - совместимо с Python 3.11+"""
    def __init__(self, items: List[T], total_count: int, page: int, per_page: int):
        self.items = items
        self.total_count = total_count
        self.page = page
        self.per_page = per_page
        self.total_pages = ceil(total_count / per_page) if per_page > 0 else 1
        self.has_prev = page > 1
        self.has_next = page < self.total_pages
        self.prev_page = page - 1 if self.has_prev else None
        self.next_page = page + 1 if self.has_next else None


def paginate_list(items: List[T], page: int = 1, per_page: int = 10) -> PaginationResult[T]:
    total_count = len(items)

    start_index = (page - 1) * per_page
    end_index = start_index + per_page

    page_items = items[start_index:end_index]

    return PaginationResult(items=page_items, total_count=total_count, page=page, per_page=per_page)


def get_pagination_info(total_count: int, page: int = 1, per_page: int = 10) -> dict[str, Any]:
    total_pages = ceil(total_count / per_page) if per_page > 0 else 1

    return {
        'total_count': total_count,
        'page': page,
        'per_page': per_page,
        'total_pages': total_pages,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'prev_page': page - 1 if page > 1 else None,
        'next_page': page + 1 if page < total_pages else None,
        'offset': (page - 1) * per_page,
    }


def get_page_numbers(current_page: int, total_pages: int, max_visible: int = 5) -> list[int]:
    if total_pages <= max_visible:
        return list(range(1, total_pages + 1))

    half_visible = max_visible // 2
    start_page = max(1, current_page - half_visible)
    end_page = min(total_pages, start_page + max_visible - 1)

    if end_page - start_page + 1 < max_visible:
        start_page = max(1, end_page - max_visible + 1)

    return list(range(start_page, end_page + 1))
