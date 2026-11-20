# FinTrust System Architecture

FinTrust is an event-driven AWS prototype for processing CSV financial transactions, applying deterministic risk rules, and presenting transaction insights. This document describes the **completed October 2026 capstone implementation**, not a live production banking platform. Cost-incurring AWS resources were subsequently shut down.

## Architecture overview

The [original architecture diagram](FinTrust%20Transaction%20Insights%20and%20Risk%20Monitoring%20System.jpg) is retained as capstone evidence. The diagram has not yet been visually audited against the final Step Functions workflow.

```text
React/Vite dashboard
       |
       v
Amazon API Gateway --> API/query Lambda --> RDS PostgreSQL / DynamoDB
       |
       +--> Upload request --> S3 raw bucket
                                  |
                                  v
                         Step Functions Standard
                                  |
                                  v
                            Ingest Lambda
                              |        |
                       invalid rows   valid rows
                              |        |
                         S3 quarantine SQS FIFO --> Score Lambda
                                                    |      |
                                                    v      v
                                               RDS PostgreSQL
                                                      DynamoDB
                                                    |
                                              High-risk alert
                                                    |
                                               Alert Lambda --> SES

Step Functions --> DynamoDB upload tracking (poll until COMPLETED / FAILED)
               --> Alert Lambda --> SES upload completion / failure notice

EventBridge --> Report Lambda --> RDS queries --> S3 CSV and JSON reports
```

This is a logical component overview, not a claim that every path runs synchronously. Ingestion also writes validated records as Parquet to the processed S3 bucket.

## Core components

| Component | Entry point or trigger | Responsibility |
| --- | --- | --- |
| Ingestion Lambda | Step Functions input or S3 event | Read CSV, validate records, quarantine invalid rows, enqueue valid transactions and export processed Parquet |
| Scoring Lambda | SQS FIFO | Persist transactions, evaluate risk rules, update relational and DynamoDB records, initiate high-risk alert handling |
| Alert Lambda | Risk event or Step Functions notification state | Send high-risk, upload-completed and upload-failed emails through SES |
| Query/API Lambda | API Gateway | Serve transaction, insight, upload, flag and resolution operations |
| Reporting Lambda | EventBridge schedule | Query PostgreSQL, generate monthly CSV/JSON reports and store them in S3 |
| Step Functions Standard | Upload workflow execution | Start ingestion, poll DynamoDB for upload status and invoke terminal notification handling |

Source modules are in [`backend/fintrust/`](../../backend/fintrust/).

## Transaction ingestion and asynchronous processing

1. An upload request is accepted through the API and its CSV is stored in the raw S3 bucket.
2. The ingestion Lambda parses the CSV and validates each row using `validators.py`.
3. Invalid rows are written to the S3 quarantine bucket with validation errors.
4. Valid rows are sent to an SQS FIFO queue for scoring. The account ID is used as the message group ID, providing ordering within each account group.
5. The scoring Lambda consumes queued transactions and persists transaction and risk information.
6. A dead-letter queue supports isolation of messages that repeatedly fail processing.
7. The ingestion code also writes processed valid records as compressed Parquet to S3.

The ingestion and scoring stages are decoupled. A successful HTTP upload acceptance is not the same as completed transaction scoring.

## Step Functions upload orchestration

The **final deployed definition**, confirmed for the capstone, is [`fintrust-upload-workflow.json`](../../fintrust-upload-workflow.json). It is a Standard state machine with a one-hour timeout.

```text
StartIngestion (invoke ingest Lambda)
     |
     v
WaitForProcessing (10 seconds)
     |
     v
CheckUploadStatus (DynamoDB getItem)
     |
     v
EvaluateUploadStatus
     |            |                  |
  COMPLETED      FAILED          missing / pending
     |            |                  |
     v            v                  +--> wait and poll again
SendUpload      SendUpload
CompletionEmail FailureEmail
     |            |
     v            v
UploadCompleted UploadFailed
  (Succeed)       (Fail)
```

- DynamoDB table: `fintrust-prod-upload-tracking`
- Tracking record: partition key `upload_id`, sort key `record_type = SUMMARY`
- Completed status invokes the alert Lambda with `notification_type = UPLOAD_COMPLETED`.
- Failed status invokes the alert Lambda with `notification_type = UPLOAD_FAILED`.
- An ingestion Lambda invocation error is caught and routed to the failure-notification state.
- Errors raised by either notification task are caught, allowing the workflow to reach its corresponding terminal state. **A terminal workflow state does not, by itself, prove an email was delivered.**

The alert Lambda checks the upload summary and uses a conditional DynamoDB notification record to prevent duplicate claims. Its notification behavior is implemented in [`alert.py`](../../backend/fintrust/alert.py).

The separate [`infrastructure/step-functions/upload-workflow.asl.json`](../../infrastructure/step-functions/upload-workflow.asl.json) is an **earlier simplified definition** without email-notification states. Keep it for historical reference, but use the root definition when discussing the final capstone workflow.

## Risk scoring

The rule engine is implemented in [`score.py`](../../backend/fintrust/score.py).

| Rule | Condition | Points |
| --- | --- | ---: |
| `HIGH_AMOUNT` | Transaction amount > R50,000 | 30 |
| `HIGH_VELOCITY` | More than 10 account transactions in the preceding one-hour window | 40 |
| `CROSS_BORDER` | Source country differs from destination country | 20 |

The classification logic is:

- **HIGH:** `HIGH_AMOUNT` or `HIGH_VELOCITY` is triggered, **or** the score reaches 60.
- **MEDIUM:** Otherwise, the score is at least 30.
- **LOW:** Otherwise.

These are project-defined risk indicators, not fraud findings or automated compliance decisions.

## Data stores

**RDS PostgreSQL** holds the relational transaction ledger and related records, including customers, accounts, transactions, risk events and alerts. The SQL schema is in [`data/sql/schema.sql`](../../data/sql/schema.sql).

**DynamoDB** supports risk-event data and upload tracking. The upload workflow specifically reads the `SUMMARY` record keyed by `upload_id` and `record_type`.

**Amazon S3** stores raw CSV uploads, quarantined invalid rows, processed Parquet files and generated monthly reports.

## REST API and frontend

The React/Vite frontend lives in [`frontend/`](../../frontend/) and consumes the backend API to display transaction and risk information.

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/transactions` | Retrieve, search, filter and paginate transactions |
| GET | `/insights` | Retrieve aggregate transaction and risk metrics |
| POST | `/upload` | Accept a CSV upload for asynchronous processing |
| POST | `/flag` | Flag a transaction or account for review |
| POST | `/resolve` | Record a review resolution |

API Gateway was used for the capstone API. The hosted API and dashboard should not be assumed to be currently available because the AWS environment was shut down.

## Reporting and notifications

The reporting Lambda reads SQL reporting queries, generates **CSV and JSON** monthly risk reports, and writes them to the configured S3 reports bucket. The EventBridge reporting schedule was disabled after the capstone to control costs.

The alert Lambda handles both high-risk transaction notifications and Step Functions upload completion/failure notifications through Amazon SES. Email delivery depends on the active SES environment and its permissions.

## Security, observability and testing

The capstone used IAM roles, VPC networking for private database access, Systems Manager Parameter Store, and AWS monitoring services. CloudWatch provides Lambda logs, custom ingestion metrics and alarms; X-Ray supports distributed tracing.

Testing is organised into [unit](../../tests/unit/), [integration](../../tests/integration/) and [end-to-end](../../tests/e2e/) suites. The [GitHub Actions CI workflow](../../.github/workflows/ci.yml) runs unit tests on pushes and pull requests, integration tests on pushes to `develop`, and AWS end-to-end tests only when manually triggered with the required environment and credentials.

For design trade-offs, gaps and future improvements, see the [Well-Architected self-assessment](well-architected-self-assessment.md). This is a project self-assessment, not an AWS-certified review.

## Scope and lifecycle

This document describes the **original capstone architecture**. Further development will be tracked as portfolio-product enhancements rather than retroactively presented as features of the October 2026 submission. The AWS environment is currently shut down to avoid ongoing charges; code and documentation remain available for review.
