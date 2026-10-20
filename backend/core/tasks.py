from celery import shared_task
from django.core.management import call_command


@shared_task(ignore_result=True)
def limpiar_resultados_de_tareas() -> None:
    """Los resultados de django.tasks se guardan en la BD (django-tasks-db): sin limpiar, la tabla crece sin fin."""
    call_command("prune_db_task_results", queue_name="*", min_age_days=14, failed_min_age_days=30)
