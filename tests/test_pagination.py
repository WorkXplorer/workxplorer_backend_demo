from django.test import SimpleTestCase
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from config.pagination import CustomPagination
from core.schema import postprocess_schema_responses


class CustomPaginationTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def test_next_previous_are_numeric_pages(self):
        request = Request(self.factory.get("/items", {"limit": 10, "offset": 20}))
        paginator = CustomPagination()

        page = paginator.paginate_queryset(list(range(35)), request)
        response = paginator.get_paginated_response(page)

        self.assertEqual(response.data["next"], 4)
        self.assertEqual(response.data["previous"], 2)
        self.assertEqual(response.data["limit"], 10)
        self.assertEqual(response.data["offset"], 20)

    def test_first_page_has_no_previous(self):
        request = Request(self.factory.get("/items", {"limit": 10, "offset": 0}))
        paginator = CustomPagination()

        page = paginator.paginate_queryset(list(range(8)), request)
        response = paginator.get_paginated_response(page)

        self.assertIsNone(response.data["next"])
        self.assertIsNone(response.data["previous"])
        self.assertEqual(response.data["limit"], 10)
        self.assertEqual(response.data["offset"], 0)


class PaginationSchemaTests(SimpleTestCase):
    def test_pagination_info_documents_numeric_next_previous(self):
        result = {
            "paths": {},
            "components": {"schemas": {}},
        }

        output = postprocess_schema_responses(
            result=result,
            generator=None,
            request=None,
            public=True,
        )

        pagination_info = output["components"]["schemas"]["PaginationInfo"]
        self.assertEqual(pagination_info["properties"]["next"]["type"], "integer")
        self.assertEqual(pagination_info["properties"]["previous"]["type"], "integer")
