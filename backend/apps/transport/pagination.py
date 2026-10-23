from rest_framework.pagination import PageNumberPagination


class OnePageNumberPagination(PageNumberPagination):
    """PageNumberPagination without its COUNT(*) query when the list fits on one page.

    Every list here does (PAGE_SIZE is 500), and the extra query is a round trip to
    the database (~170 ms to the hosted Supabase) on every list request. The first
    page fetches one row more than a page: when that row is missing, the rows fetched
    are the whole list and their number is the count. Longer lists and later pages
    are paginated as before. The response shape does not change.
    """

    def paginate_queryset(self, queryset, request, view=None):
        page_size = self.get_page_size(request)
        if not page_size or request.query_params.get(self.page_query_param, "1") not in ("", "1"):
            return super().paginate_queryset(queryset, request, view)
        rows = list(queryset[:page_size + 1])
        if len(rows) > page_size:
            return super().paginate_queryset(queryset, request, view)
        self.request = request
        self.page = self.django_paginator_class(rows, page_size).page(1)
        return rows
