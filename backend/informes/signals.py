from django.dispatch import Signal

# Argumentos: informe, enviar (bool: si hay que mandarlo por email). Lo escuchan las notificaciones.
informe_generado = Signal()
