# core/exceptions.py
class ErrorDeDominio(Exception):
    """Base de los errores de negocio. Cada subclase dice cómo se ve en la API."""

    codigo = "error_de_dominio"
    status = 409
    mensaje = "La operación no es posible en el estado actual."

    def __init__(self, mensaje: str | None = None, **contexto):
        super().__init__(mensaje or self.mensaje)
        self.mensaje = mensaje or self.mensaje
        self.contexto = contexto
