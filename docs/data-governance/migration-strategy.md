# FinTrust Transaction Insights and Risk Monitoring System

## Legacy System Migration Strategy

**Project:** FinTrust Transaction Insights and Risk Monitoring System

**Document Type:** Data Migration Strategy

**Assessment Stage:** Final Project Review

---

## 1. Purpose

This document describes how FinTrust's legacy transaction data and processing environment could be migrated from the existing flat-file NAS system to the AWS-based transaction monitoring architecture.

The strategy uses the AWS 7 Rs migration framework to classify the migration approach and identifies the AWS service required by the capstone design.

The migration approach is designed to minimise disruption while providing a controlled path from the legacy environment to the modern cloud architecture.

---

## 2. Legacy Environment

The existing FinTrust environment is based on a legacy flat-file NAS system.

Transaction information is stored in files rather than in the normalised relational and NoSQL data stores used by the new AWS architecture.

The legacy environment therefore presents several limitations:

* File-based transaction storage
* Limited real-time processing capabilities
* Limited automated risk scoring
* Limited integration with modern APIs
* Increased operational effort for reporting and monitoring
* Less flexible scalability compared with the target cloud architecture

The target AWS environment provides centralised transaction storage, automated validation, risk scoring, monitoring, reporting, and alerting.

---

## 3. Target AWS Architecture

The migrated environment will use the FinTrust AWS architecture:

**Legacy NAS → AWS migration → S3 → Validation/Processing → RDS PostgreSQL + DynamoDB → Risk Monitoring → API / Reporting / Alerts**

The main target services include:

* **Amazon S3** for raw transaction files, quarantine data, and reporting outputs
* **AWS Lambda** for validation and processing
* **Amazon RDS for PostgreSQL** for the core transaction ledger
* **Amazon DynamoDB** for risk events and fast-access risk information
* **Amazon SQS FIFO** for ordered transaction processing
* **Amazon API Gateway** for controlled API access
* **Amazon EventBridge** for scheduled processing
* **Amazon SES** for risk and compliance notifications
* **Amazon CloudWatch and X-Ray** for monitoring and tracing

---

## 4. 7 Rs Classification

### Selected Strategy: Rehost

The FinTrust legacy migration is classified primarily as **Rehost** under the AWS 7 Rs framework.

Rehosting means moving an existing workload to AWS with minimal changes to the original environment.

For FinTrust, the initial migration stage would preserve the existing transaction files and structure as much as possible while moving the legacy workload into the AWS environment.

This approach reduces migration complexity and allows the organisation to establish the cloud environment before performing further application and data modernisation.

---

## 5. Required AWS Migration Service

The capstone requires the migration strategy to identify **AWS Application Migration Service** as the migration service.

**AWS Application Migration Service (MGN)** supports the migration of existing workloads into AWS while reducing the amount of change required during the initial migration stage.

For the FinTrust scenario, it provides the migration mechanism required by the capstone's migration strategy and supports the initial Rehost approach.

The migrated workload can then be progressively modernised into the target cloud-native architecture.

---

## 6. Migration Approach

The migration would be performed in controlled stages.

### Stage 1: Discovery and Assessment

The legacy NAS environment would first be assessed to identify:

* Transaction files
* File formats
* Data volumes
* Data dependencies
* Data quality issues
* Existing processing requirements
* Security and access requirements
* Retention requirements

The migration team would also identify which legacy processes can be retired, replaced, or modernised.

### Stage 2: Prepare the AWS Environment

The required AWS infrastructure would be prepared before moving production data.

This includes:

* S3 storage
* Private networking
* IAM roles
* RDS PostgreSQL
* DynamoDB
* Lambda processing
* Monitoring
* Security controls
* Required configuration and secrets management

Security and access controls would be established before migration rather than added afterwards.

### Stage 3: Initial Migration

The legacy workload would be migrated using the selected Rehost strategy.

Existing files would be transferred into the AWS environment while maintaining their original structure where practical.

The migrated data would initially be treated as raw source data.

### Stage 4: Validation and Transformation

Once migrated, the data would pass through the FinTrust validation process.

The ingestion Lambda would validate required fields, data types, transaction information, and other defined business rules.

Valid records would continue to the transaction processing pipeline.

Invalid records would be sent to the S3 quarantine location and excluded from the main transaction ledger.

### Stage 5: Load into Target Data Stores

Validated transaction data would be transformed into the structures required by the new architecture.

The core transaction ledger would be stored in RDS PostgreSQL.

Risk events and fast-access risk information would be stored in DynamoDB where appropriate.

Database constraints and application validation would be used to protect data integrity.

### Stage 6: Testing and Reconciliation

Before completing the migration, the migrated data would be compared against the legacy source.

Validation would include:

* Record counts
* Transaction totals
* Required fields
* Duplicate records
* Invalid records
* Account relationships
* Date ranges
* Risk information

Any discrepancies would be investigated before the migrated dataset was considered ready.

### Stage 7: Cutover

After successful validation, transaction processing would move to the new AWS environment.

The legacy system would be retained temporarily according to the approved retention and rollback strategy before being decommissioned.

---

## 7. Future Modernisation

Rehosting provides the initial migration path, but it is not intended to be the final state of the platform.

After the legacy workload has been successfully migrated and stabilised, FinTrust can progressively modernise the workload using AWS-native services.

Potential modernisation activities include:

* Moving raw transaction processing into S3 and Lambda
* Replacing legacy file-based processing with event-driven workflows
* Loading validated transactions into RDS PostgreSQL
* Using DynamoDB for high-speed risk-event access
* Introducing automated risk scoring
* Exposing transaction insights through API Gateway
* Automating scheduled reporting with EventBridge
* Automating compliance alerts through SES
* Expanding CloudWatch monitoring and operational visibility

This creates a controlled progression from the legacy environment to the target cloud-native architecture rather than attempting a high-risk transformation in a single migration step.

---

## 8. Migration Risks and Controls

| Risk                                 | Impact | Control                                                        |
| ------------------------------------ | ------ | -------------------------------------------------------------- |
| Data loss during migration           | High   | Pre-migration backups, record-count reconciliation, validation |
| Invalid or corrupted records         | High   | Lambda validation and S3 quarantine                            |
| Unauthorised access during migration | High   | IAM least privilege, private networking, controlled access     |
| Migration downtime                   | Medium | Staged migration, validation before cutover, rollback planning |
| Data structure incompatibility       | Medium | Data profiling, transformation and post-migration validation   |

---

## 9. 7 Rs Decision Summary

| 7 Rs Strategy               | Applicability to FinTrust                                                                                 |
| --------------------------- | --------------------------------------------------------------------------------------------------------- |
| **Retain**                  | Not preferred because the objective is to move away from the legacy NAS environment                       |
| **Retire**                  | Not appropriate initially because the transaction workload must continue operating                        |
| **Rehost**                  | **Selected initial strategy.** Minimises changes during the first migration stage                         |
| **Relocate**                | Not selected because the target architecture requires more than moving the existing environment unchanged |
| **Replatform**              | Suitable as a later modernisation stage when workloads are adapted to AWS-managed services                |
| **Repurchase**              | Not selected because FinTrust is building a custom transaction monitoring platform                        |
| **Refactor / Re-architect** | Appropriate as a later stage for fully cloud-native redesign, but not as the initial migration approach   |

---

## 10. Conclusion

FinTrust's legacy flat-file NAS migration is classified as **Rehost** under the AWS 7 Rs framework.

The migration strategy uses **AWS Application Migration Service** as required by the capstone and follows a staged approach that separates initial migration from later modernisation.

The approach reduces migration risk by first moving the existing workload with minimal change, then validating and transforming the data into the FinTrust AWS architecture.

This provides a controlled path from the legacy environment to a scalable, event-driven cloud platform while preserving data integrity, security, and operational continuity.