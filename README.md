# AI-Powered Transaction Processing Pipeline

Backend + DevOps internship assignment submission.

## What this project does

This FastAPI backend accepts a dirty financial transactions CSV file, creates a background processing job, cleans the data, detects anomalies, classifies missing categories, generates a summary, and exposes polling APIs to check job status and results.

## Tech Stack

- FastAPI for REST APIs
- PostgreSQL for persistence
- Redis + Celery for background job processing
- Pandas for CSV cleaning and analytics
- Gemini API optional for LLM classification, with rule-based fallback
- Docker Compose for one-command setup

## Architecture

Client uploads CSV to FastAPI. FastAPI stores a Job row in PostgreSQL with `pending` status and enqueues the job in Redis. Celery worker picks up the job, reads the CSV, cleans rows, detects anomalies, classifies missing categories, stores transactions and summary in PostgreSQL, then marks the job as `completed` or `failed`.

## Setup Instructions

### 1. Clone the repository

```bash
git clone <your-github-repo-link>
cd alemeno_assignment
```

### 2. Create environment file

```bash
cp .env.example .env
```

Optional: add your Gemini key in `.env` and set `USE_LLM=true`. Without it, the project uses a deterministic rule-based fallback so the system still works.

### 3. Start the full system

```bash
docker compose up --build
```

API will run at:

```text
http://localhost:8000
```

Swagger docs:

```text
http://localhost:8000/docs
```

## Example curl Requests

### Upload CSV

```bash
curl -X POST "http://localhost:8000/jobs/upload" \
  -F "file=@transactions.csv"
```

Example response:

```json
{
  "job_id": 1,
  "status": "pending",
  "message": "File uploaded and processing started"
}
```

### Check job status

```bash
curl "http://localhost:8000/jobs/1/status"
```

### Get processed results

```bash
curl "http://localhost:8000/jobs/1/results"
```

### List all jobs

```bash
curl "http://localhost:8000/jobs"
```

### Filter jobs by status

```bash
curl "http://localhost:8000/jobs?status=completed"
```

## Data Cleaning Rules

- Dates are normalized to ISO format: `YYYY-MM-DD`
- Currency symbols are removed from amounts
- Currency and status values are uppercased
- Blank categories are classified using Gemini or fallback rules
- Exact duplicate rows are removed

## Anomaly Detection Rules

A transaction is flagged as anomalous when:

- Its amount is greater than 3x the median amount of that account
- Currency is USD but the merchant is domestic-only such as Swiggy, Ola, IRCTC, or Zomato
- Notes contain suspicious keywords such as `SUSPICIOUS`

## API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/jobs/upload` | Upload CSV and start background job |
| GET | `/jobs/{job_id}/status` | Poll job status |
| GET | `/jobs/{job_id}/results` | Get cleaned transactions, anomalies, and summary |
| GET | `/jobs` | List jobs, optionally filter by status |

## Data Model

### Job

Stores uploaded job metadata: filename, status, row counts, created time, completed time, and error message.

### Transaction

Stores cleaned transaction rows including merchant, amount, currency, status, category, anomaly flag, anomaly reason, and LLM details.

### JobSummary

Stores total spend by currency, top merchants, anomaly count, narrative, and risk level.

## Scaling Discussion

The current implementation works well for small CSV files and internship-level evaluation. At 100x traffic, the main breaking points would be database connection limits, Celery worker capacity, Redis queue pressure, file storage, and LLM rate limits. In production, I would add horizontal API scaling, multiple Celery worker replicas, cloud object storage for uploaded files, connection pooling, batch database inserts, rate-limited LLM batching, observability, and retries with a dead-letter queue.
