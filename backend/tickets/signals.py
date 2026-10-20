from django.dispatch import Signal

# Se emite al terminar el pipeline (con éxito, para revisar o con error).
# Argumentos: ticket. El módulo 76 lo conecta con las notificaciones en tiempo real.
ticket_terminado = Signal()
