from datetime import datetime
import pandas as pd
from app.celery_app import celery
from app.database import SessionLocal
from app.models import Job, Transaction, JobSummary
from app.processing import clean_dataframe, detect_anomalies, gemini_category, build_summary

@celery.task(name="app.tasks.process_job")
def process_job(job_id: int, file_path: str):
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return
        job.status = "processing"
        db.commit()

        raw_df = pd.read_csv(file_path)
        job.row_count_raw = len(raw_df)
        df = clean_dataframe(raw_df)
        df = detect_anomalies(df)

        for _, row in df.iterrows():
            category = row.get("category") or ""
            llm_category = None
            llm_raw = None
            llm_failed = False
            if not category or category.lower() in ["nan", "", "none"]:
                category, llm_raw, llm_failed = gemini_category(row.get("merchant"), row.get("amount"), row.get("currency"), row.get("notes"))
                llm_category = category

            txn = Transaction(
                job_id=job.id,
                txn_id=None if pd.isna(row.get("txn_id")) else str(row.get("txn_id")),
                date=row.get("date"),
                merchant=row.get("merchant"),
                amount=row.get("amount"),
                currency=row.get("currency"),
                status=row.get("status"),
                category=category,
                account_id=row.get("account_id"),
                is_anomaly=bool(row.get("is_anomaly")),
                anomaly_reason=row.get("anomaly_reason") or None,
                llm_category=llm_category,
                llm_raw_response=llm_raw,
                llm_failed=llm_failed,
            )
            db.add(txn)

        summary_data = build_summary(df)
        summary = JobSummary(job_id=job.id, **summary_data)
        db.add(summary)
        job.row_count_clean = len(df)
        job.status = "completed"
        job.completed_at = datetime.utcnow()
        db.commit()
    except Exception as exc:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = "failed"
            job.error_message = str(exc)
            db.commit()
    finally:
        db.close()
