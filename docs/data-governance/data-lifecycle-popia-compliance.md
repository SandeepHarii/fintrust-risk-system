# FinTrust Transaction Insights and Risk Monitoring System

## Data Lifecycle and POPIA Compliance Statement

**Project:** FinTrust Transaction Insights and Risk Monitoring System

**Document Type:** Data Governance and Compliance Statement

**Assessment Stage:** Final Project Review

---

## 1. Purpose

This statement explains how FinTrust handles transaction and related data throughout its lifecycle and how the system applies data governance principles aligned with the Protection of Personal Information Act (POPIA).

FinTrust is a capstone transaction monitoring system and does not process real customer banking data. The system uses synthetic project data to demonstrate secure transaction ingestion, validation, storage, risk analysis, retrieval, and alerting.

The main goals are to minimise unnecessary data exposure, restrict access to authorised components, protect sensitive information, and avoid keeping data longer than it is needed for its intended purpose.

---

## 2. Data Classification

FinTrust processes several types of information:

| Data Category      | Examples                                                 | Classification           | Protection                                                         |
| ------------------ | -------------------------------------------------------- | ------------------------ | ------------------------------------------------------------------ |
| Customer Data      | Customer ID, name, contact information                   | Personal / Confidential  | Restricted access, encryption, controlled database access          |
| Account Data       | Account ID, account status, account relationship         | Confidential             | IAM, private RDS, security groups                                  |
| Transaction Data   | Transaction ID, account ID, amount, date, type, location | Confidential / Financial | Private database access, encryption, controlled application access |
| Risk Data          | Risk score, risk flags, risk events                      | Confidential / Sensitive | IAM-controlled access, DynamoDB/RDS access restrictions            |
| Alert Data         | Risk alert details and compliance notifications          | Confidential             | Restricted application access and controlled SES delivery          |
| Raw CSV Files      | Uploaded transaction records                             | Confidential             | S3 access controls, encryption, controlled processing              |
| Application Logs   | Processing events, errors, request information           | Internal / Operational   | CloudWatch access controls and restricted IAM permissions          |
| Configuration Data | Application configuration and protected parameters       | Restricted               | SSM Parameter Store and IAM permissions                            |

No real customer financial information is required or used by the capstone implementation.

---

## 3. Data Lifecycle

FinTrust manages data through the following stages:

### 1. Collection

Transaction data enters the system through CSV ingestion and is stored in Amazon S3.

Only information needed for transaction processing, risk scoring, reporting, and monitoring should be collected.

### 2. Validation and Processing

The ingestion Lambda validates incoming records.

Invalid records are separated from valid transaction data and placed into quarantine storage instead of being written to the main transaction ledger.

Valid transactions continue through the processing pipeline.

### 3. Storage

Valid transaction data is stored in Amazon RDS for PostgreSQL.

Risk-related information is also stored in DynamoDB where fast access to risk events is required.

S3 stores raw transaction files as well as relevant reporting and quarantine objects.

### 4. Use and Access

Application components access data based on their responsibilities.

IAM policies control AWS service permissions, while private RDS networking and security groups restrict database access.

The API provides controlled access to transaction and risk information.

### 5. Reporting and Alerting

Risk information can be used to generate compliance alerts through Amazon SES and scheduled reports through the reporting workflow.

Only the information needed for the relevant alert or report should be included.

### 6. Retention and Disposal

Data should not be kept indefinitely without a defined business or project purpose.

When data is no longer required, it should be securely deleted or handled according to the applicable retention requirement.

For the capstone environment, synthetic project data may be removed after the assessment and demonstration activities are complete.

---

## 4. Retention Tiers

FinTrust uses a tiered retention model based on how frequently data is accessed and how long it needs to remain available.

| Tier            | Data                                       |                                    Retention Period | Storage / Purpose                                             |
| --------------- | ------------------------------------------ | --------------------------------------------------: | ------------------------------------------------------------- |
| **Hot**         | Active transaction, account, and risk data |                                       **12 months** | RDS PostgreSQL for frequently accessed operational data       |
| **Warm**        | Historical transaction and analytical data |                                   **Up to 3 years** | S3 for less frequently accessed historical and reporting data |
| **Cold**        | Long-term archived transaction data        |                                   **Up to 7 years** | S3 Glacier for long-term archival                             |
| **Quarantine**  | Invalid transaction records                |             **Temporary, until review or disposal** | S3 quarantine storage                                         |
| **Operational** | Logs, metrics, and tracing information     | **According to configured monitoring requirements** | CloudWatch operational monitoring                             |

The 7-year cold retention period follows the capstone's specified archival lifecycle requirement. In a production banking environment, final retention periods would be determined by applicable legislation, regulatory requirements, contractual obligations, and the organisation's approved retention policy.

Because FinTrust uses synthetic capstone data, project data may be removed after the assessment and demonstration period when it is no longer required.

---

## 5. Access Controls

FinTrust applies least-privilege principles to protect data:

* IAM roles are used for AWS workloads instead of embedding AWS credentials in application code.
* Lambda functions receive only the permissions required for their specific responsibilities.
* RDS is deployed privately rather than being publicly accessible.
* Security groups restrict database connectivity.
* S3 access is controlled through AWS permissions.
* SSM Parameter Store keeps application configuration out of source code.
* API Gateway provides controlled access to application endpoints.
* Temporary administrative infrastructure and SSH access used for database seeding were removed after the task was completed.
* Development and production configuration should remain separated.

Together, these controls reduce the risk of unauthorised access and unnecessary exposure of sensitive information.

---

## 6. POPIA Alignment

The FinTrust design supports several key POPIA principles:

**Purpose limitation:** Data is collected and processed for defined transaction monitoring, risk scoring, reporting, and alerting purposes.

**Data minimisation:** The system should only process information that is necessary for its intended functions.

**Security safeguards:** IAM, private networking, security groups, encryption, controlled configuration, and restricted service permissions are used to protect data.

**Access control:** Access is limited according to application and infrastructure responsibilities.

**Retention limitation:** Data should not be retained longer than necessary for its defined purpose and applicable requirements.

**Accountability:** Data handling controls and architectural decisions are documented so that the treatment of information can be reviewed.

Because FinTrust is a capstone project that uses synthetic data, this document demonstrates POPIA-aligned design principles rather than claiming full legal compliance for a production banking environment.

---

## 7. Governance Summary

FinTrust follows a simple data lifecycle:

**Collect → Validate → Store → Process → Report/Alert → Retain → Dispose**

The architecture combines data classification, least-privilege access, private database networking, controlled configuration, encryption, and defined retention periods to reduce unnecessary exposure of transaction and personal information.

For a production deployment, the governance model would need to be expanded with formal retention schedules, clearly defined data-owner responsibilities, legal and regulatory review, stronger audit capabilities, and processes for handling data-subject requests and other POPIA obligations.