from rest_framework.pagination import LimitOffsetPagination, PageNumberPagination
from rest_framework.exceptions import ValidationError
from rest_framework.utils.urls import remove_query_param
from urllib.parse import urlsplit, parse_qsl, urlencode, urlunsplit


class LinkSanitizerPaginationMixin:
    allowed_link_query_params = None
    remove_link_query_params = ()

    def _sanitize_link(self, url):
        if not url:
            return url

        cleaned_url = url
        for query_param in self.remove_link_query_params:
            cleaned_url = remove_query_param(cleaned_url, query_param)

        if not self.allowed_link_query_params:
            return cleaned_url

        split_url = urlsplit(cleaned_url)
        query_pairs = parse_qsl(split_url.query, keep_blank_values=True)
        allowed_pairs = [
            (key, value)
            for key, value in query_pairs
            if key in self.allowed_link_query_params
        ]
        filtered_query = urlencode(allowed_pairs, doseq=True)

        return urlunsplit(
            (
                split_url.scheme,
                split_url.netloc,
                split_url.path,
                filtered_query,
                split_url.fragment,
            )
        )

    def get_next_link(self):
        return self._sanitize_link(super().get_next_link())

    def get_previous_link(self):
        return self._sanitize_link(super().get_previous_link())


class CustomPagination(LinkSanitizerPaginationMixin, LimitOffsetPagination):
    """
    Secure LimitOffset pagination that strictly validates limit and offset
    as non-negative integers, preventing SQL injection via query parameters.

    Response includes limit/offset so the StandardJSONRenderer can build
    a proper pagination object.
    """

    default_limit = 20
    limit_query_param = "limit"
    offset_query_param = "offset"
    max_limit = 100
    remove_link_query_params = ("page",)

    def get_paginated_response(self, data):
        """
        Return paginated response with limit and offset included.
        The StandardJSONRenderer will extract these into the pagination object.
        """
        response = super().get_paginated_response(data)
        limit = self.get_limit(self.request)
        if limit is None:
            limit = self.default_limit

        offset = self.get_offset(self.request)
        if offset is None:
            offset = 0

        current_page = (offset // limit) + 1 if limit > 0 else 1
        next_page = current_page + 1 if (offset + limit) < self.count else None
        previous_page = current_page - 1 if current_page > 1 else None

        # Keep limit/offset and expose next/previous as numeric page pointers.
        response.data['next'] = next_page
        response.data['previous'] = previous_page
        response.data['limit'] = limit
        response.data['offset'] = offset
        return response

    def get_limit(self, request):
        """Validate and return the limit parameter as a safe integer."""
        raw = request.query_params.get(self.limit_query_param)
        if raw is not None:
            try:
                limit = int(raw)
            except (ValueError, TypeError):
                raise ValidationError(
                    {self.limit_query_param: "Must be a valid integer."}
                )
            if limit < 0:
                raise ValidationError(
                    {self.limit_query_param: "Must be a non-negative integer."}
                )
        return super().get_limit(request)

    def get_offset(self, request):
        """Validate and return the offset parameter as a safe integer."""
        raw = request.query_params.get(self.offset_query_param)
        if raw is not None:
            try:
                offset = int(raw)
            except (ValueError, TypeError):
                raise ValidationError(
                    {self.offset_query_param: "Must be a valid integer."}
                )
            if offset < 0:
                raise ValidationError(
                    {self.offset_query_param: "Must be a non-negative integer."}
                )
        return super().get_offset(request)


class RecruiterProfilePagination(PageNumberPagination):
    page_size = 6
    page_size_query_param = "page_size"
    max_page_size = 100


class StudentListPagination(CustomPagination):
    default_limit = 20
    allowed_link_query_params = {"edupartner_id", "status", "limit", "offset"}
    remove_link_query_params = ()

    def get_paginated_response(self, data):
        from rest_framework.response import Response

        limit = self.get_limit(self.request)
        if limit is None:
            limit = self.default_limit
            
        offset = self.get_offset(self.request)
        if offset is None:
            offset = 0

        current_page = (offset // limit) + 1 if limit > 0 else 1
        next_page = current_page + 1 if (offset + limit) < self.count else None
        previous_page = current_page - 1 if current_page > 1 else None

        return Response(
            {
                "results": data,         
                "count": self.count,
                "next": next_page,
                "previous": previous_page,
                "limit": limit,
                "offset": offset,
            }
        )
