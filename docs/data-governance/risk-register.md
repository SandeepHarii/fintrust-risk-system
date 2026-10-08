# FinTrust Transaction Insights and Risk Monitoring System

## Data Governance Risk Register

**Project:** FinTrust Transaction Insights and Risk Monitoring System

**Document Type:** Data Governance Risk Register

**Assessment Stage:** Final Project Review

---

## 1. Purpose

This risk register identifies key data governance risks associated with the FinTrust transaction monitoring system and the AWS controls used to reduce those risks.

The risks focus on the confidentiality, integrity, availability, and appropriate handling of transaction and risk-related data.

---

## 2. Risk Register

| ID      | Data Governance Risk                                                           | Probability | Impact | Risk Level | Named AWS Control                            | Control Application                                                                                                                                                                     |
| :------ | :----------------------------------------------------------------------------- | :---------- | :----- | :--------- | :------------------------------------------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **R01** | **Unauthorised access to sensitive transaction or account data**               | Medium      | High   | High       | **IAM Least Privilege**                      | Lambda execution roles are restricted to the AWS actions and resources required for their specific responsibilities. RDS is private and access is restricted through security groups.   |
| **R02** | **Invalid or corrupted transaction data entering the main transaction ledger** | Medium      | High   | High       | **AWS Lambda Validation + S3 Quarantine**    | The ingestion process validates transaction records before persistence. Invalid records are separated into quarantine storage rather than being written to the main transaction ledger. |
| **R03** | **Loss or unintended exposure of transaction data stored in AWS services**     | Low         | High   | Medium     | **Amazon S3 Encryption and Access Controls** | Transaction files are stored in controlled S3 locations with restricted AWS permissions and encryption. Access is limited to authorised application components and users.               |

---

## 3. Risk Details

### R01 — Unauthorised Access to Sensitive Data

**Risk:**
Unauthorised access to transaction, account, or risk information could expose confidential financial information or allow inappropriate modification of data.

**Probability:** Medium

**Impact:** High

**AWS Control:** IAM Least Privilege

**Mitigation:**
FinTrust uses IAM roles for AWS workloads and restricts permissions according to each component's responsibilities. RDS is deployed in private networking and security groups restrict database connectivity. API access is also controlled through API Gateway.

---

### R02 — Invalid or Corrupted Data Entering the Ledger

**Risk:**
Invalid, incomplete, or malformed transaction records could enter the main transaction ledger and affect risk scoring, reporting, or downstream analysis.

**Probability:** Medium

**Impact:** High

**AWS Control:** AWS Lambda Validation + S3 Quarantine

**Mitigation:**
The ingestion Lambda validates incoming transaction records before they are persisted. Records that fail validation are separated into quarantine storage and prevented from entering the main transaction ledger. This protects downstream processing from known invalid input.

---

### R03 — Data Loss or Unintended Exposure

**Risk:**
Transaction files or other sensitive data stored in AWS services could be lost, incorrectly exposed, or accessed by an unauthorised component.

**Probability:** Low

**Impact:** High

**AWS Control:** Amazon S3 Encryption and Access Controls

**Mitigation:**
S3 storage is protected using AWS access controls and encryption. Bucket access is limited to authorised application components, reducing the likelihood of accidental or unauthorised data exposure.

---

## 4. Governance Summary

The three risks are addressed through controls built into the FinTrust architecture rather than relying solely on operational procedures.

The main governance approach is:

**Restrict Access → Validate Data → Protect Stored Data → Monitor Processing**

These controls support the confidentiality, integrity, and appropriate handling of FinTrust transaction data.

This register represents the controls implemented or designed for the capstone environment. A production banking deployment would require additional controls, formal risk ownership, ongoing risk reviews, incident response procedures, and regulatory oversight.
