from .celery_app import celery_app
from ..database import SessionLocal
from ..services.processing import process_document


@celery_app.task(name="app.workers.tasks.process_document")
def process_document_task(document_id: int):
    db = SessionLocal()
    try:
        process_document(db, document_id)
    finally:
        db.close()
