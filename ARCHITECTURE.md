# High-Level Architecture Diagram

```text
User / Evaluator
      |
      | POST /jobs/upload CSV
      v
FastAPI API Service
      |
      | 1. Create Job(status=pending)
      | 2. Save uploaded CSV
      | 3. Push job_id to Redis queue
      v
PostgreSQL <---------------- Celery Worker
      ^                         |
      |                         | Read CSV
      |                         | Clean data
      |                         | Detect anomalies
      |                         | Classify missing categories
      |                         | Generate summary
      |                         v
      +-------------------- Store Transactions + Summary

User polls:
GET /jobs/{job_id}/status
GET /jobs/{job_id}/results
```

## Request Lifecycle

1. Client uploads `transactions.csv` to `/jobs/upload`.
2. API validates the file type.
3. API creates a `Job` row with status `pending`.
4. API saves the CSV file and enqueues a Celery task.
5. Worker updates the job to `processing`.
6. Worker reads the CSV using Pandas.
7. Worker normalizes dates, amounts, casing, categories, and duplicates.
8. Worker flags anomalies.
9. Worker stores cleaned transactions and summary.
10. Worker marks job as `completed`.
11. Client polls status/results endpoints.
```
