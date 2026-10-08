# FinTrust Transaction Insights and Risk Monitoring System

## Data Quality and Validation Framework

**Project:** FinTrust Transaction Insights and Risk Monitoring System

**Document Type:** Data Quality and Validation Framework

**Assessment Stage:** Final Project Review

### 1. Purpose

This framework defines how FinTrust maintains the quality, accuracy, completeness, and integrity of transaction data throughout the ingestion process.

The system validates transaction records before they are written to the main transaction ledger. Records that fail validation are not inserted into the main database and are sent to an S3 quarantine location for review.

### 2. Data Quality Dimensions

| Quality Dimension | FinTrust Approach                                                                                                      |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------- |
| **Accuracy**      | Transaction values and fields are checked against the expected data format and validation rules before persistence.    |
| **Completeness**  | Required fields must be present before a transaction can be accepted.                                                  |
| **Validity**      | Fields must contain values in the expected format and allowed range.                                                   |
| **Consistency**   | Transaction records must follow the defined schema and data types used by the application and PostgreSQL database.     |
| **Uniqueness**    | Transaction identifiers are used to prevent duplicate transaction records where uniqueness is required.                |
| **Timeliness**    | Transactions are processed through the ingestion pipeline when uploaded and validated before entering the main ledger. |

### 3. Validation Rules

The ingestion process applies validation checks to incoming transaction records, including:

* Required fields are present.
* Transaction identifiers follow the expected format.
* Account identifiers are present and valid.
* Transaction dates contain valid date values.
* Transaction amounts contain valid numeric values.
* Transaction types contain permitted values.
* Location and other required fields follow the expected format.
* Records must satisfy the database constraints defined in the PostgreSQL schema.

### 4. Invalid Data Handling

The validation process follows this flow:

**CSV Upload → S3 Raw Storage → Lambda Validation → Validation Result**

**Valid record:**

* Continues through the ingestion process.
* Can be persisted to the main transaction ledger.
* Can continue to risk scoring and downstream processing.

**Invalid record:**

* Is rejected from the main transaction ledger.
* Is sent to the S3 quarantine location.
* Does not continue as a valid transaction through the processing pipeline.
* Can be reviewed or corrected separately.

This prevents invalid or malformed records from contaminating the main transaction dataset.

### 5. Data Integrity Controls

Data quality is reinforced through controls at multiple layers:

* **Application validation:** Lambda validation checks incoming records before persistence.
* **Database constraints:** PostgreSQL primary keys, foreign keys, `NOT NULL` constraints, indexes, and data types enforce structural integrity.
* **Quarantine:** Invalid records are isolated in S3 rather than inserted into the main ledger.
* **Error handling:** Processing failures are handled separately from successfully validated records.
* **Logging:** Application processing and validation events are recorded through CloudWatch logging.
* **Risk validation:** Accepted transactions are passed through the defined risk-scoring rules.

### 6. Data Quality Outcome

The framework separates transaction data into two clear outcomes:

**Accepted → validated → persisted → processed**

**Rejected → quarantined → excluded from main ledger**

This provides a controlled data-quality boundary between raw uploaded data and trusted transaction data used for risk monitoring and reporting.

### 7. Governance Summary

FinTrust applies data quality controls at the point where data enters the system rather than relying only on downstream correction.

The combination of application validation, database constraints, S3 quarantine, controlled processing, and logging supports the **accuracy, completeness, validity, consistency, uniqueness, and timeliness** of transaction data used by the system.
