"""Nombres de los grupos de la channel layer (letras, números, guiones, puntos y _; menos de 100 caracteres)."""


def de_usuario(usuario_id: int) -> str:
    return f"usuario_{usuario_id}"


def de_hogar(hogar_id: int) -> str:
    return f"hogar_{hogar_id}"
