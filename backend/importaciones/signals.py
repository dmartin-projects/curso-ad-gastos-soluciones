from django.dispatch import Signal

# Argumentos: importacion. Los escucha el módulo 76 (notificaciones y barra de progreso en tiempo real).
importacion_analizada = Signal()
importacion_progreso = Signal()
importacion_terminada = Signal()
