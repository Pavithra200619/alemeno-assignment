import os, shutil
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import Base, engine, get_db
from app.models import Job, Transaction, JobSummary
from app.tasks import process_job

Base.metadata.create_all(bind=engine)
UPLOAD_DIR = Path("/app/uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI(title="AI-Powered Transaction Processing Pipeline")

@app.get("/")
def root():
    return {"message": "Transaction Processing API is running", "docs": "/docs"}

@app.post("/jobs/upload")
def upload_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are allowed")
    job = Job(filename=file.filename, status="pending")
    db.add(job)
    db.commit()
    db.refresh(job)

    file_path = UPLOAD_DIR / f"job_{job.id}_{file.filename}"
    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    process_job.delay(job.id, str(file_path))
    return {"job_id": job.id, "status": job.status, "message": "File uploaded and processing started"}

@app.get("/jobs/{job_id}/status")
def get_status(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    response = {
        "job_id": job.id,
        "filename": job.filename,
        "status": job.status,
        "row_count_raw": job.row_count_raw,
        "row_count_clean": job.row_count_clean,
        "created_at": job.created_at,
        "completed_at": job.completed_at,
        "error_message": job.error_message,
    }
    if job.status == "completed" and job.summary:
        response["summary"] = {
            "total_spend_inr": job.summary.total_spend_inr,
            "total_spend_usd": job.summary.total_spend_usd,
            "anomaly_count": job.summary.anomaly_count,
            "risk_level": job.summary.risk_level,
            "narrative": job.summary.narrative,
        }
    return response

@app.get("/jobs/{job_id}/results")
def get_results(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "completed":
        raise HTTPException(status_code=400, detail=f"Job is {job.status}; results are available only after completion")
    transactions = db.query(Transaction).filter(Transaction.job_id == job_id).all()
    return {
        "job_id": job.id,
        "summary": {
            "total_spend_inr": job.summary.total_spend_inr,
            "total_spend_usd": job.summary.total_spend_usd,
            "top_merchants": job.summary.top_merchants,
            "anomaly_count": job.summary.anomaly_count,
            "narrative": job.summary.narrative,
            "risk_level": job.summary.risk_level,
        },
        "transactions": [
            {
                "txn_id": t.txn_id,
                "date": t.date,
                "merchant": t.merchant,
                "amount": t.amount,
                "currency": t.currency,
                "status": t.status,
                "category": t.category,
                "account_id": t.account_id,
                "is_anomaly": t.is_anomaly,
                "anomaly_reason": t.anomaly_reason,
            } for t in transactions
        ]
    }

@app.get("/jobs")
def list_jobs(status: str | None = Query(default=None), db: Session = Depends(get_db)):
    query = db.query(Job)
    if status:
        query = query.filter(Job.status == status)
    jobs = query.order_by(Job.created_at.desc()).all()
    return [{"job_id": j.id, "filename": j.filename, "status": j.status, "row_count_raw": j.row_count_raw, "created_at": j.created_at} for j in jobs]
