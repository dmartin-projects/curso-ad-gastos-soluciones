"""IA de mentira compatible con Chat Completions (módulo 83, ejercicio 4): responde siempre el mismo ticket."""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

DATOS = {
    "comercio": "Mercadona",
    "nif": "",
    "fecha": "2026-10-12",
    "total": 4.85,
    "moneda": "EUR",
    "categoria": "Supermercado",
    "lineas": [{"descripcion": "Leche", "cantidad": 1, "precio_unitario": 4.85}],
    "confianza": 0.95,
}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        respuesta = {"choices": [{"message": {"role": "assistant", "content": json.dumps(DATOS)}}]}
        cuerpo = json.dumps(respuesta).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(cuerpo)


HTTPServer(("0.0.0.0", 9100), Handler).serve_forever()
