# FinTrust Security and IAM Plan

## 1. Purpose

This document defines the security, identity, access management, encryption, network security, storage security, and messaging controls for the FinTrust Transaction Insights and Risk Monitoring System.

The design follows these principles:

* Least-privilege access
* Dedicated IAM roles per Lambda function
* Private database access
* No hard-coded credentials
* Encryption at rest and in transit
* Secure configuration through AWS Systems Manager Parameter Store
* API authentication and controlled access
* S3 public-access prevention
* SQS dead-letter handling
* CloudWatch monitoring and X-Ray tracing
* Cost-aware AWS architecture

The implementation prioritises AWS Free Tier eligible services and configurations where practical and uses the allocated AWS credits for required services or usage outside Free Tier allowances.

---

## 2. Security Principles

The FinTrust platform follows these core security principles:

1. **Least privilege**
   Each AWS Lambda function receives only the permissions required for its specific responsibilities.

2. **Dedicated IAM roles**
   Each Lambda function uses its own execution role rather than sharing a broad role.

3. **Private database access**
   PostgreSQL is deployed without public access and can only be reached through the required private network path.

4. **No hard-coded credentials**
   Database credentials and sensitive configuration are stored in AWS Systems Manager Parameter Store.

5. **Encryption at rest**
   AWS-managed encryption is used for supported AWS resources.

6. **Encryption in transit**
   HTTPS/TLS is used for API and service communication where applicable.

7. **API protection**
   API Gateway uses API keys and usage plans to control client access.

8. **S3 protection**
   S3 buckets use Block Public Access and server-side encryption.

9. **Failure isolation**
   Failed SQS messages are moved to a FIFO dead-letter queue after configured retry attempts.

10. **Observability**
    CloudWatch Logs, metrics, alarms, and X-Ray provide operational visibility.

11. **Cost awareness**
    Unnecessary paid infrastructure such as NAT Gateway and customer-managed KMS keys is avoided.

---

## 3. IAM Role Matrix

Each Lambda function has a dedicated execution role.

| Lambda      | Required Access                                                                                           |
| ----------- | --------------------------------------------------------------------------------------------------------- |
| `ingest.py` | S3 read/write, SQS send, DynamoDB write, SSM read, CloudWatch Logs, X-Ray                                 |
| `score.py`  | SQS receive/delete, RDS access, DynamoDB read/write, invoke `alert.py`, SSM read, CloudWatch Logs, X-Ray  |
| `alert.py`  | SES send, SSM read, CloudWatch Logs, X-Ray                                                                |
| `query.py`  | RDS access, DynamoDB read/query, S3 access required for upload workflow, SSM read, CloudWatch Logs, X-Ray |
| `report.py` | RDS access, S3 report write, SSM read, CloudWatch Logs, X-Ray                                             |

### IAM Restrictions

The following restrictions apply:

* No Lambda role uses unrestricted `Action: "*"` permissions.
* No Lambda role can access unrelated AWS resources.
* Lambda roles cannot modify IAM users, roles, policies, or permissions.
* S3 access is restricted to the required FinTrust buckets and prefixes.
* SQS permissions are restricted to the required transaction queue and DLQ.
* DynamoDB permissions are restricted to the FinTrust tables required by each function.
* Lambda invocation permissions are restricted to explicitly required functions.
* Database access is restricted to the required RDS resource and network path.
* SSM access is restricted to the FinTrust configuration parameters.
* AWS credentials are never stored in source code.
* Permissions are reviewed against the actual implementation before deployment.

---

## 4. RDS Network Security

The PostgreSQL database is designed as a private database resource.

### Controls

* Public accessibility is disabled.
* RDS is deployed in private subnets.
* A dedicated RDS security group is used.
* PostgreSQL port `5432` is restricted.
* Inbound database access is permitted only from the FinTrust Lambda security group.
* No unrestricted internet access is permitted to the database.
* No `0.0.0.0/0` inbound rule is used for PostgreSQL.
* No NAT Gateway is required for the architecture.

### Network Flow

```text
Lambda
   |
   v
Lambda Security Group
   |
   v
RDS Security Group
   |
   v
Private RDS PostgreSQL
```

This prevents direct public access to the transaction database.

---

## 5. S3 Security

S3 is used for transaction file ingestion, processed data, quarantined files, and generated reports.

### Security Controls

All FinTrust S3 buckets must:

* Block all public access.
* Use server-side encryption.
* Prevent public bucket policies.
* Restrict access through IAM.
* Avoid unnecessary cross-account access.
* Use unique bucket names.
* Store only required application data.
* Apply appropriate lifecycle policies where required.

Sensitive transaction files must never be exposed through public S3 URLs.

---

## 6. AWS Storage and Messaging Resources

The following AWS resources form the core storage and messaging layer.

| Resource                          | Purpose                               | Security Controls                                           |
| --------------------------------- | ------------------------------------- | ----------------------------------------------------------- |
| `fintrust-raw-*` S3 bucket        | Raw transaction CSV uploads           | Block Public Access, server-side encryption, IAM            |
| `fintrust-processed-*` S3 bucket  | Validated/processed transaction data  | Block Public Access, server-side encryption, IAM            |
| `fintrust-quarantine-*` S3 bucket | Invalid or rejected transaction files | Block Public Access, server-side encryption, restricted IAM |
| `fintrust-reports-*` S3 bucket    | Generated monthly reports             | Block Public Access, server-side encryption, restricted IAM |
| `fintrust-transaction-queue.fifo` | Ordered transaction processing        | FIFO queue, restricted producer/consumer access             |
| `fintrust-transaction-dlq.fifo`   | Failed message isolation              | FIFO DLQ, restricted access, redrive policy                 |

### Resource Flow

```text
API Gateway
     |
     v
POST /upload
     |
     v
S3 Raw Bucket
     |
     v
ingest.py
     |
     +--------------------+
     |                    |
     v                    v
Valid                  Invalid
     |                    |
     v                    v
SQS FIFO              S3 Quarantine
     |
     v
score.py
     |
     +--------------------+
     |                    |
     v                    v
RDS PostgreSQL       DynamoDB
     |
     v
Risk Processing
     |
     v
alert.py
     |
     v
SES
```

### Failed Message Flow

```text
SQS FIFO
   |
   v
score.py
   |
   +---- Success ----> Processing Complete
   |
   +---- Failure ----> Retry
                         |
                         v
                       DLQ
```

### Resource Naming

S3 bucket names must use a unique suffix because S3 bucket names are globally unique.

Example naming pattern:

```text
fintrust-raw-<unique-suffix>
fintrust-processed-<unique-suffix>
fintrust-quarantine-<unique-suffix>
fintrust-reports-<unique-suffix>
```

The FIFO queue and DLQ must use the `.fifo` suffix:

```text
fintrust-transaction-queue.fifo
fintrust-transaction-dlq.fifo
```

Final deployed resource names will be recorded in the deployment evidence.

### Deployment Evidence

The implementation will capture evidence for:

* S3 bucket creation
* S3 Block Public Access configuration
* S3 encryption configuration
* SQS FIFO queue configuration
* SQS FIFO DLQ configuration
* SQS redrive policy
* S3 event notification
* IAM permissions
* Lambda integration

---

## 7. Encryption Strategy

FinTrust uses AWS-managed encryption where appropriate to protect data at rest.

### Encryption Controls

| Resource                  | Encryption                                      |
| ------------------------- | ----------------------------------------------- |
| S3                        | AWS-managed server-side encryption              |
| RDS PostgreSQL            | Encryption at rest using an AWS-managed KMS key |
| DynamoDB                  | AWS-managed encryption at rest                  |
| SSM SecureString          | AWS-managed `aws/ssm` KMS key                   |
| API Gateway               | HTTPS/TLS                                       |
| AWS service communication | TLS/HTTPS where supported                       |

### KMS Cost Control

The project does not create customer-managed KMS keys unless a specific requirement makes one necessary.

This avoids unnecessary key-management overhead and associated costs.

AWS-managed encryption is preferred where it satisfies the security requirement.

---

## 8. AWS Systems Manager Parameter Store

Sensitive configuration is stored in AWS Systems Manager Parameter Store rather than source code.

### Example Parameters

```text
/fintrust/prod/db/host
/fintrust/prod/db/name
/fintrust/prod/db/user
/fintrust/prod/db/password
/fintrust/prod/ses/compliance-recipient
```

### Sensitive Parameters

Sensitive values such as passwords are stored as:

```text
SecureString
```

The application retrieves configuration at runtime.

### Security Controls

* No database passwords in Git.
* No AWS access keys in source code.
* Sensitive parameters use SecureString.
* Lambda roles receive only the required `ssm:GetParameter` access.
* Parameters are scoped to the FinTrust application.
* AWS-managed SSM encryption is used.

---

## 9. API Gateway Security

The FinTrust REST API is exposed through Amazon API Gateway.

### Security Controls

* HTTPS/TLS only.
* API key authentication.
* Usage plan configured for controlled access.
* Request validation where applicable.
* No AWS credentials exposed to API consumers.
* No database credentials exposed through API responses.
* Generic error responses prevent unnecessary internal information disclosure.
* Sensitive application configuration remains server-side.

### API Authentication

Clients provide the API key using:

```text
x-api-key
```

The API Gateway usage plan controls permitted API consumption.

---

## 10. SQS and Dead-Letter Queue Security

The transaction processing queue uses Amazon SQS FIFO to preserve ordered processing.

### FIFO Queue

```text
fintrust-transaction-queue.fifo
```

The queue provides ordered transaction processing and supports account-level message grouping.

### Dead-Letter Queue

```text
fintrust-transaction-dlq.fifo
```

Messages that repeatedly fail processing are moved to the DLQ rather than being retried indefinitely.

### Security Controls

* Only `ingest.py` can send transaction messages.
* Only `score.py` can consume transaction messages.
* Queue access is restricted through IAM.
* DLQ access is restricted.
* A redrive policy controls movement of failed messages.
* CloudWatch monitoring identifies failed processing.
* DLQ contents are reviewed during testing.

---

## 11. CloudWatch and X-Ray

CloudWatch provides logging, monitoring, and operational visibility across the application.

### Structured Logging

Lambda functions produce structured JSON logs containing relevant information such as:

```text
timestamp
function
request_id
correlation_id
operation
status
error
risk_event
```

Logs must not contain:

* Database passwords
* AWS credentials
* API keys
* Unnecessary personal information
* Sensitive transaction information unless required for troubleshooting

### X-Ray

AWS X-Ray is used to trace application requests and identify service-level failures.

Tracing covers relevant Lambda and AWS service interactions.

---

## 12. Cost-Controlled Architecture

AWS costs are treated as an architecture constraint.

The following controls are applied:

* Avoid NAT Gateway.
* Avoid customer-managed KMS keys unless required.
* Avoid unnecessary always-on compute.
* Stop the RDS database outside required lab/demo periods where appropriate.
* Prefer AWS Free Tier eligible configurations.
* Use allocated AWS credits for required usage outside Free Tier allowances.
* Avoid unnecessary duplicate resources.
* Monitor AWS billing and usage during development.
* Delete temporary resources after testing where they are no longer required.

The project does not introduce additional AWS services unless they provide a clear requirement or rubric benefit.

---

## 13. Security Validation Checklist

Before the system is considered deployment-ready, the following controls must be verified:

### IAM

* [ ] Dedicated IAM role exists for each Lambda.
* [ ] No wildcard IAM actions.
* [ ] No unnecessary resource permissions.
* [ ] Lambda roles cannot modify IAM.
* [ ] S3 permissions are resource-restricted.
* [ ] SQS permissions are resource-restricted.
* [ ] DynamoDB permissions are resource-restricted.
* [ ] SSM permissions are parameter-restricted.
* [ ] Lambda invocation permissions are restricted.

### RDS

* [ ] Public access disabled.
* [ ] RDS deployed in private networking.
* [ ] Security group restricts port `5432`.
* [ ] Database is accessible only from the required Lambda network path.
* [ ] RDS encryption at rest enabled.

### S3

* [ ] Block Public Access enabled.
* [ ] Server-side encryption enabled.
* [ ] IAM-only access configured.
* [ ] Raw bucket created.
* [ ] Processed bucket created.
* [ ] Quarantine bucket created.
* [ ] Reports bucket created.

### SQS

* [ ] FIFO queue created.
* [ ] FIFO DLQ created.
* [ ] Redrive policy configured.
* [ ] Producer permissions restricted.
* [ ] Consumer permissions restricted.
* [ ] DLQ failure scenario tested.

### API

* [ ] HTTPS/TLS enabled.
* [ ] API key authentication configured.
* [ ] Usage plan configured.
* [ ] No credentials exposed through API responses.
* [ ] Request validation implemented where required.

### Configuration

* [ ] SSM parameters created.
* [ ] Sensitive values stored as SecureString.
* [ ] No secrets committed to Git.
* [ ] Lambda functions retrieve configuration at runtime.

### Monitoring

* [ ] CloudWatch Logs enabled.
* [ ] Structured JSON logging implemented.
* [ ] Required metrics configured.
* [ ] Required alarms configured.
* [ ] X-Ray tracing enabled where required.

### Cost

* [ ] No NAT Gateway deployed.
* [ ] No unnecessary customer-managed KMS keys.
* [ ] RDS usage controlled.
* [ ] AWS credits monitored.
* [ ] Unnecessary resources removed after testing.
* [ ] Billing evidence captured.

---

## 14. Security Evidence

The final project evidence should include screenshots or exported configuration demonstrating the implemented controls.

Required evidence includes:

1. IAM role permissions
2. S3 Block Public Access
3. S3 encryption
4. SQS FIFO configuration
5. SQS DLQ and redrive policy
6. RDS private/public access configuration
7. RDS security group
8. SSM Parameter Store configuration
9. API Gateway API key and usage plan
10. CloudWatch Logs
11. CloudWatch metrics/alarms
12. X-Ray tracing
13. AWS billing/credit usage
14. Successful DLQ test
15. Successful end-to-end transaction processing