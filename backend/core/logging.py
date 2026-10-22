# core/logging.py
import logging
import re
import uuid
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
# Lo envía el cliente o el proxy: solo se acepta con forma de id (un "\n" inyectaría líneas falsas en los logs)
ID_VALIDO = re.compile(r"[A-Za-z0-9-]{1,64}")


class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_var.get()
        return True


def request_id_middleware(get_response):
    def middleware(request):
        recibido = request.headers.get("X-Request-ID", "")  # el proxy o Angular pueden enviarlo
        rid = recibido if ID_VALIDO.fullmatch(recibido) else uuid.uuid4().hex
        token = request_id_var.set(rid)
        try:
            response = get_response(request)
        finally:
            request_id_var.reset(token)
        response["X-Request-ID"] = rid  # el cliente puede reportarlo
        return response

    return middleware
