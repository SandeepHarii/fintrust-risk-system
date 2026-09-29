## System Architecture

FinTrust uses an event-driven AWS architecture to ingest, validate, score, store, query, and report on financial transactions. Processing is separated into specialised Lambda functions so that each component has a clear responsibility.

### Lambda Functions

| Lambda Function | Trigger                 | Responsibility                                                                                                                                                                             |
| --------------- | ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `ingest.py`     | Amazon S3               | Receives uploaded CSV transactions, parses and validates the records, sanitises input, sends invalid records to the quarantine bucket, and sends valid transactions to the SQS FIFO queue. |
| `score.py`      | Amazon SQS FIFO         | Processes validated transactions, applies the FinTrust risk-scoring rules, determines the risk level, and stores the results in RDS PostgreSQL and DynamoDB.                               |
| `alert.py`      | High-risk scoring event | Sends high-risk transaction alerts to compliance officers through Amazon SES.                                                                                                              |
| `query.py`      | Amazon API Gateway      | Handles API requests for transaction data, risk insights, transaction uploads, manual account flagging, and resolution actions.                                                            |
| `report.py`     | Amazon EventBridge      | Runs the monthly reporting process, executes SQL analytics, generates CSV and JSON reports, and stores them in Amazon S3.                                                                  |

### Risk Scoring

The scoring Lambda evaluates transactions using the following rules:

* **HIGH_AMOUNT** — transaction amount greater than R50,000
* **HIGH_VELOCITY** — more than 10 transactions within one hour
* **CROSS_BORDER** — transaction identified as cross-border

The final risk score and risk level are stored for later querying and reporting.

### API Endpoints

The FinTrust REST API is exposed through Amazon API Gateway and protected using API key authentication and usage plans.

| Method | Endpoint        | Purpose                                                                                                                |
| ------ | --------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `GET`  | `/transactions` | Retrieve transaction records with filtering and pagination.                                                            |
| `GET`  | `/insights`     | Retrieve aggregated transaction and risk insights for monitoring and dashboards.                                       |
| `POST` | `/upload`       | Accept a transaction CSV upload for asynchronous processing. Returns `202 Accepted` once the upload has been accepted. |
| `POST` | `/flag`         | Manually flag an account or transaction for compliance review.                                                         |
| `POST` | `/resolve`      | Resolve an existing compliance or risk event after review.                                                             |

### Asynchronous Upload Flow

The `/upload` endpoint does not process the entire CSV synchronously. After the upload is accepted, processing continues through the event-driven pipeline:

```text
POST /upload
      ↓
API Gateway
      ↓
query.py
      ↓
S3 Raw Transaction Bucket
      ↓
ingest.py
      ↓
SQS FIFO
      ↓
score.py
```

This allows transaction ingestion and risk processing to happen independently while SQS provides reliable, ordered processing.