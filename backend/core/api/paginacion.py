from rest_framework.pagination import CursorPagination, PageNumberPagination
from rest_framework.response import Response


class PaginacionEstandar(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"  # ?page_size=50
    max_page_size = 100  # 🔐 sin máximo, ?page_size=1000000

    def get_paginated_response(self, data):
        return Response(
            {
                "count": self.page.paginator.count,
                "total_pages": self.page.paginator.num_pages,
                "page": self.page.number,
                "page_size": self.get_page_size(self.request),
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )

    def get_paginated_response_schema(self, schema):  # para que OpenAPI documente la forma (módulo 38)
        base = super().get_paginated_response_schema(schema)
        base["properties"].update(
            {
                "total_pages": {"type": "integer"},
                "page": {"type": "integer"},
                "page_size": {"type": "integer"},
            }
        )
        return base


class PaginacionCursor(CursorPagination):
    """Para listados largos con scroll infinito (movimientos): rendimiento constante y estable."""

    page_size = 50
    ordering = ("-fecha", "-id")
