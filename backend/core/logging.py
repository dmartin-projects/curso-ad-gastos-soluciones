# core/logging.py
import logging
import uuid
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_var.get()
        return True


def request_id_middleware(get_response):
    def middleware(request):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex  # el proxy puede enviarlo
        token = request_id_var.set(rid)
        try:
            response = get_response(request)
        finally:
            request_id_var.reset(token)
        response["X-Request-ID"] = rid  # el cliente puede reportarlo
        return response

    return middleware
