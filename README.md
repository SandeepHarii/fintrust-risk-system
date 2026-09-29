# FinTrust Transaction Insights and Risk Monitoring System

## Overview

The **FinTrust Transaction Insights and Risk Monitoring System** is a cloud-based transaction processing and risk monitoring platform designed for FinTrust Bank SA.

The system receives transaction data from legacy systems, validates and processes the data, applies rule-based risk scoring, stores transaction and risk information, exposes secure APIs for users, sends alerts for high-risk activity, and generates monthly risk reports.

The solution is designed using AWS managed services with an event-driven and serverless architecture.

---

## Business Objective

The system is designed to help FinTrust:

* Process transaction data reliably
* Identify potentially high-risk transaction activity
* Give compliance teams access to transaction and risk insights
* Automatically alert compliance officers about high-risk activity
* Provide executive leadership with recurring risk reports
* Maintain appropriate security, governance and data lifecycle controls

The project does **not** implement machine-learning fraud detection or make automated real-world compliance decisions.

---

# System Architecture

The core transaction flow is:

```text
Legacy Transaction System
          │
          │ CSV
          ▼
    Amazon S3
  Raw Transactions
          │
          │ S3 Event
          ▼
    ingest.py Lambda
          │
     ┌────┴────┐
     │         │
 Invalid     Valid
     │         │
     ▼         ▼
  S3       SQS FIFO
Quarantine     │
               ▼
         score.py Lambda
          │           │
          ▼           ▼
       RDS          DynamoDB
    PostgreSQL     Risk / Events
          │
          │ High Risk
          ▼
     alert.py
          │
          ▼
         SES
          │
          ▼
 Compliance Officer
```

Users access transaction and risk information through:

```text
Users
  ↓
API Gateway
  ↓
query.py Lambda
  ↓
RDS PostgreSQL + DynamoDB
```

Monthly reporting is handled through:

```text
EventBridge
     ↓
report.py Lambda
     ↓
SQL Analytics
     ↓
S3 Monthly Reports
```

---

# AWS Services

| Service                                 | Purpose                                                                        |
| --------------------------------------- | ------------------------------------------------------------------------------ |
| **Amazon S3**                           | Transaction uploads, quarantine, processed data and monthly reports            |
| **AWS Lambda**                          | Serverless transaction processing, scoring, API handling, alerts and reporting |
| **Amazon SQS FIFO**                     | Reliable ordered transaction processing                                        |
| **Amazon SQS DLQ**                      | Isolation of messages that repeatedly fail processing                          |
| **Amazon RDS PostgreSQL**               | Core relational transaction ledger                                             |
| **Amazon DynamoDB**                     | Risk scores, event log and session tokens                                      |
| **Amazon API Gateway**                  | Secure REST API                                                                |
| **Amazon SES**                          | High-risk compliance alerts                                                    |
| **Amazon EventBridge**                  | Monthly report scheduling                                                      |
| **Amazon CloudWatch**                   | Logs, metrics, alarms, dashboards and Logs Insights                            |
| **AWS X-Ray**                           | Distributed application tracing                                                |
| **AWS IAM**                             | Least-privilege access control                                                 |
| **AWS KMS**                             | Encryption key management                                                      |
| **AWS Systems Manager Parameter Store** | Application configuration                                                      |
| **Amazon VPC**                          | Network isolation for private resources                                        |

A NAT Gateway is intentionally excluded to control costs and remain within the project constraints.

---

# Lambda Functions

The application contains five core Lambda functions.

## `ingest.py`

**Trigger:** S3 Object Created

Responsible for:

* Reading uploaded CSV files
* Parsing transaction records
* Validating required fields
* Sanitising input
* Performing POPIA-aware field checks
* Sending invalid records to S3 quarantine
* Sending valid transaction events to SQS FIFO
* Producing structured logs

The ingestion function does not perform the final risk scoring.

---

## `score.py`

**Trigger:** SQS FIFO

Responsible for:

* Consuming transaction events
* Applying the defined risk rules
* Calculating a risk score
* Determining the transaction risk level
* Persisting transaction information to RDS PostgreSQL
* Persisting risk information to DynamoDB
* Triggering high-risk alert processing

Initial risk indicators include:

* **HIGH_AMOUNT:** transaction amount greater than R50,000
* **HIGH_VELOCITY:** more than 10 transactions within one hour
* **CROSS_BORDER:** transaction identified as cross-border

The final scoring weights and risk-level thresholds will be defined as part of the system design.

---

## `alert.py`

**Trigger:** High-risk scoring event

Responsible for:

* Receiving high-risk transaction results
* Creating compliance alert information
* Sending alerts through Amazon SES
* Logging alert processing

---

## `query.py`

**Trigger:** Amazon API Gateway

Responsible for handling API requests and interacting with RDS PostgreSQL and DynamoDB.

The API supports:

```text
GET  /transactions
GET  /insights
POST /upload
POST /flag
POST /resolve
```

---

## `report.py`

**Trigger:** Amazon EventBridge monthly schedule

Responsible for:

* Running SQL analytics
* Generating monthly risk reports
* Producing CSV and JSON output
* Storing reports in Amazon S3

The reporting process will use SQL features including CTEs, window functions, ranking and compliance views.

---

# API

## `GET /transactions`

Retrieves transaction records.

Supported functionality includes:

* Account filtering
* Pagination
* Transaction information
* Risk information

Example:

```text
GET /transactions?account_id=ACC001&limit=50&offset=0
```

---

## `GET /insights`

Returns aggregated transaction and risk information for monitoring and dashboard use.

Example response:

```json
{
  "total_transactions": 1250,
  "total_value": 4525000.00,
  "high_risk_transactions": 27,
  "medium_risk_transactions": 84,
  "low_risk_transactions": 1139
}
```

---

## `POST /upload`

Starts asynchronous transaction ingestion.

The API returns:

```text
202 Accepted
```

The transaction file is then processed through:

```text
S3 → ingest.py → SQS FIFO → score.py
```

---

## `POST /flag`

Allows an authorised user to manually flag an account or transaction for compliance review.

Example request:

```json
{
  "account_id": "ACC001",
  "reason": "Suspicious transaction activity"
}
```

---

## `POST /resolve`

Allows an authorised user to resolve an existing compliance or risk event.

Example request:

```json
{
  "account_id": "ACC001",
  "reason": "Reviewed and cleared"
}
```

---

# Data Storage

## Amazon RDS PostgreSQL

RDS stores the core relational transaction ledger.

The database will contain:

* `accounts`
* `transactions`
* `risk_events`
* `alerts`

The database will use:

* Primary keys
* Foreign keys
* NOT NULL constraints
* Appropriate indexes
* 3NF relational design
* Stored procedures/functions
* Compliance views
* SQL analytics queries

RDS will operate inside a private VPC subnet and will not be publicly accessible.

---

## Amazon DynamoDB

DynamoDB provides a NoSQL event and risk store.

Primary key design:

```text
Partition Key: account_id
Sort Key:      tx_timestamp
```

The table will support:

* Risk scores
* Event records
* Session tokens
* Account-based queries

---

# Data Validation and Quality

Transaction data is validated during ingestion.

Invalid records are not inserted into the main transaction pipeline.

Instead:

```text
Invalid Transaction
        ↓
S3 Quarantine
        +
Operational Logging
```

Processing failures from the SQS pipeline are isolated through the Dead-Letter Queue.

---

# Security

The system follows a least-privilege security model.

Each Lambda receives its own IAM execution role with only the permissions required for its responsibilities.

The system uses:

* AWS IAM
* AWS KMS
* Amazon VPC
* Private RDS networking
* Security Groups
* SSM Parameter Store
* API Gateway API keys and usage plans
* Encrypted S3 storage

Wildcard IAM actions are avoided.

---

# Monitoring and Observability

Amazon CloudWatch provides:

* Structured Lambda logs
* Custom metrics
* Error-rate monitoring
* High-risk transaction metrics
* DLQ monitoring
* CloudWatch alarms
* Logs Insights
* Monitoring dashboards

AWS X-Ray provides distributed tracing across the application flow.

---

# Data Lifecycle

The planned data lifecycle is:

```text
Hot
RDS PostgreSQL
12 months
       ↓
Warm
S3 Parquet
3 years
       ↓
Cold
S3 Glacier
7 years
```

The lifecycle supports the project's governance and retention requirements.

---

# Project Structure

```text
fintrust-risk-system/
│
├── fintrust/
│   ├── __init__.py
│   ├── config.py
│   ├── db.py
│   ├── dynamo.py
│   ├── models.py
│   ├── validators.py
│   ├── ingest.py
│   ├── score.py
│   ├── alert.py
│   ├── query.py
│   └── report.py
│
├── tests/
│   ├── conftest.py
│   ├── unit/
│   └── integration/
│
├── sql/
│   ├── schema.sql
│   ├── seed.sql
│   ├── risk_report.sql
│   ├── monthly_summary.sql
│   ├── views.sql
│   └── functions.sql
│
├── docs/
├── infrastructure/
├── evidence/
│
├── .github/
│   └── workflows/
│       └── ci.yml
│
├── .env.example
├── .gitignore
├── README.md
└── requirements.txt
```

---

# Development Status

### Completed

* Project scope defined
* Official project requirements mapped
* AWS architecture designed
* Architecture diagram completed
* Lambda responsibilities defined
* API endpoints defined
* GitHub repository established
* Development and main branches established
* Python development environment established

### In Progress

* AWS infrastructure deployment
* SSM configuration
* IAM Lambda execution roles
* 3NF database design
* RDS PostgreSQL setup
* DynamoDB setup
* Python data-access layer
* Security and storage configuration

### Planned

* Transaction ingestion
* Risk scoring
* API implementation
* Alerting
* Monthly reporting
* Automated testing
* CI/CD
* Monitoring
* End-to-end testing
* Final documentation
* Live demonstration

---

# Project Goals

The completed system must demonstrate:

* Event-driven AWS architecture
* Serverless application development
* Relational and NoSQL data modelling
* Python application development
* Secure API design
* Automated risk monitoring
* Data governance
* Automated testing and CI/CD
* Cloud observability
* Production-quality engineering practices