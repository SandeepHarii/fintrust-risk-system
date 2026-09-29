## API Design

The FinTrust API provides a secure REST interface for transaction querying, risk insights, transaction uploads, and compliance account actions.

The API is exposed through **Amazon API Gateway** and processed by the `query.py` Lambda function. API access is protected using an **API key and usage plan**.

### Base URL

```text
https://{api-id}.execute-api.{region}.amazonaws.com/{stage}
```

The deployed API Gateway URL will be added once the API is deployed.

### Authentication

All API endpoints require:

```http
x-api-key: <API_KEY>
```

API Gateway validates the API key before forwarding requests to the Lambda backend.

No AWS credentials or database credentials are exposed to API consumers.

---

## Endpoints

| Method | Endpoint        | Purpose                                                     |
| ------ | --------------- | ----------------------------------------------------------- |
| GET    | `/transactions` | Retrieve transactions with pagination and account filtering |
| GET    | `/insights`     | Retrieve transaction and risk insights                      |
| POST   | `/upload`       | Initiate an asynchronous transaction CSV upload             |
| POST   | `/flag`         | Manually flag an account for risk monitoring                |
| POST   | `/resolve`      | Resolve an existing compliance alert                        |

---

## GET /transactions

Retrieves transaction records from the PostgreSQL transaction ledger.

### Query Parameters

| Parameter    | Type    | Required | Description                    |
| ------------ | ------- | -------- | ------------------------------ |
| `account_id` | UUID    | No       | Filter transactions by account |
| `limit`      | Integer | No       | Number of records to return    |
| `offset`     | Integer | No       | Number of records to skip      |

Example:

```http
GET /transactions?account_id=123e4567-e89b-12d3-a456-426614174000&limit=20&offset=0
```

### Response

```json
{
  "items": [
    {
      "transaction_id": "123e4567-e89b-12d3-a456-426614174000",
      "account_id": "987e6543-e21b-12d3-a456-426614174000",
      "tx_date": "2026-10-01T10:30:00",
      "amount": 75000.00,
      "currency": "ZAR",
      "transaction_type": "TRANSFER",
      "source_country": "ZA",
      "destination_country": "ZA",
      "risk_flag": "HIGH_AMOUNT"
    }
  ],
  "limit": 20,
  "offset": 0,
  "total": 1
}
```

### Status Codes

| Status | Meaning                             |
| ------ | ----------------------------------- |
| `200`  | Transactions retrieved successfully |
| `400`  | Invalid query parameters            |
| `401`  | Missing or invalid API key          |
| `500`  | Internal server error               |

---

## GET /insights

Retrieves aggregated transaction and risk information for monitoring and compliance analysis.

### Query Parameters

| Parameter    | Type | Required | Description                            |
| ------------ | ---- | -------- | -------------------------------------- |
| `account_id` | UUID | No       | Return insights for a specific account |
| `start_date` | Date | No       | Start of analysis period               |
| `end_date`   | Date | No       | End of analysis period                 |

Example:

```http
GET /insights?account_id=123e4567-e89b-12d3-a456-426614174000
```

### Response

```json
{
  "account_id": "123e4567-e89b-12d3-a456-426614174000",
  "transaction_count": 42,
  "total_amount": 385000.00,
  "high_risk_count": 5,
  "risk_levels": {
    "HIGH": 3,
    "MEDIUM": 2,
    "LOW": 37
  }
}
```

### Status Codes

| Status | Meaning                         |
| ------ | ------------------------------- |
| `200`  | Insights retrieved successfully |
| `400`  | Invalid query parameters        |
| `401`  | Missing or invalid API key      |
| `404`  | Account not found               |
| `500`  | Internal server error           |

---

## POST /upload

Initiates an asynchronous transaction CSV upload.

The API does **not** wait for the complete ingestion and scoring process.

The request is accepted and the transaction-processing workflow continues asynchronously through Amazon S3, Lambda and SQS.

### Request

```json
{
  "file_name": "transactions_2026_10.csv",
  "content_type": "text/csv"
}
```

### Response

```json
{
  "message": "Upload accepted for processing",
  "file_name": "transactions_2026_10.csv",
  "status": "accepted"
}
```

### Status Codes

| Status | Meaning                                     |
| ------ | ------------------------------------------- |
| `202`  | Upload accepted for asynchronous processing |
| `400`  | Invalid upload request                      |
| `401`  | Missing or invalid API key                  |
| `500`  | Internal server error                       |

The `202 Accepted` response indicates that processing has been accepted but has not necessarily completed.

---

## POST /flag

Manually flags an account for risk monitoring.

The operation uses the PostgreSQL stored function `flag_account()` to create the risk event and update the account status atomically.

### Request

```json
{
  "account_id": "123e4567-e89b-12d3-a456-426614174000",
  "reason": "Suspicious transaction activity"
}
```

### Response

```json
{
  "message": "Account flagged successfully",
  "account_id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "FLAGGED"
}
```

### Status Codes

| Status | Meaning                      |
| ------ | ---------------------------- |
| `200`  | Account flagged successfully |
| `400`  | Invalid request              |
| `401`  | Missing or invalid API key   |
| `404`  | Account not found            |
| `500`  | Internal server error        |

---

## POST /resolve

Resolves an existing compliance alert.

### Request

```json
{
  "alert_id": "123e4567-e89b-12d3-a456-426614174000",
  "resolution_reason": "Reviewed and cleared by compliance"
}
```

### Response

```json
{
  "message": "Alert resolved successfully",
  "alert_id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "RESOLVED"
}
```

### Status Codes

| Status | Meaning                     |
| ------ | --------------------------- |
| `200`  | Alert resolved successfully |
| `400`  | Invalid request             |
| `401`  | Missing or invalid API key  |
| `404`  | Alert not found             |
| `409`  | Alert is already resolved   |
| `500`  | Internal server error       |

---

## Error Response Format

API errors use a consistent JSON structure.

```json
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "account_id must be a valid UUID"
  }
}
```

Common error codes include:

| Code              | Meaning                                             |
| ----------------- | --------------------------------------------------- |
| `INVALID_REQUEST` | Request failed validation                           |
| `UNAUTHORIZED`    | API key is missing or invalid                       |
| `NOT_FOUND`       | Requested resource does not exist                   |
| `CONFLICT`        | Operation conflicts with the current resource state |
| `INTERNAL_ERROR`  | Unexpected server-side error                        |

---

## API Processing Flow

```text
API Consumer
     │
     ▼
Amazon API Gateway
     │
     │ API Key + Usage Plan
     ▼
query.py Lambda
     │
     ├── GET /transactions ──► RDS PostgreSQL
     │
     ├── GET /insights ──────► RDS + DynamoDB
     │
     ├── POST /upload ───────► S3
     │
     ├── POST /flag ─────────► PostgreSQL
     │
     └── POST /resolve ──────► PostgreSQL
```

### Asynchronous Upload Flow

```text
POST /upload
      │
      ▼
API Gateway
      │
      ▼
query.py
      │
      ▼
S3 Raw Upload Bucket
      │
      ▼
ingest.py
      │
      ▼
SQS FIFO
      │
      ▼
score.py
```

The asynchronous upload design prevents the API request from remaining open while CSV validation, transaction processing, risk scoring and database writes are performed.