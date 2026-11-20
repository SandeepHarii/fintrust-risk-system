# FinTrust Deployment and Reactivation Notes

> **Status:** Historical capstone deployment notes and a future reactivation checklist. This is **not** a one-command deployment guide. The AWS environment was shut down after the October 2026 capstone to control costs.

## Scope

FinTrust uses Amazon S3, Lambda, SQS FIFO and DLQ, RDS PostgreSQL, DynamoDB, API Gateway, Step Functions Standard, SES, EventBridge, CloudWatch, X-Ray, IAM and VPC networking. The React/Vite frontend was hosted through CloudFront and S3, with an API proxy Lambda.

See the [architecture documentation](../architecture/system-architecture.md) and [final diagram](../architecture/fintrust-final-architecture.svg).

## Before reactivation

1. **Check the AWS budget and credits.** Paid resources may incur charges immediately when provisioned.
2. **Inspect current AWS state** rather than assuming previously deployed resources still exist.
3. **Check the retained RDS snapshot** and choose whether to restore it or start with a clean demo database. Never restore real customer data.
4. **Review networking and IAM:** private database networking, security groups, Lambda execution roles, S3 access, SQS permissions and Step Functions access.
5. **Recreate required endpoints only when justified** by the actual network design and cost budget. Interface VPC endpoints can create hourly charges.
6. **Verify configuration:** environment variables, SSM parameters, database connectivity, SES sandbox restrictions and API key storage.
7. **Deploy backend services** and confirm the S3 event / upload orchestration, SQS FIFO/DLQ, risk scoring, DynamoDB tracking, alerts and reporting.
8. **Deploy the frontend** with CloudFront/S3 and API proxy configuration. Do not embed an upstream API key in client-side JavaScript.
9. **Run unit, integration and controlled end-to-end tests** with synthetic CSV data.
10. **Confirm CloudWatch alarms and billing alerts**, then perform the demonstration and shut down cost-incurring services when no longer needed.

## Source references

| Component | Repository location |
| --- | --- |
| Backend Lambda modules | [`backend/fintrust/`](../../backend/fintrust/) |
| Final upload state machine | [`fintrust-upload-workflow.json`](../../fintrust-upload-workflow.json) |
| Historical simplified state machine | [`infrastructure/step-functions/upload-workflow.asl.json`](../../infrastructure/step-functions/upload-workflow.asl.json) |
| IAM and AWS configuration examples | [`infrastructure/`](../../infrastructure/) |
| CloudFront API proxy | [`deployment/api-proxy/`](../../deployment/api-proxy/) |
| React/Vite frontend | [`frontend/`](../../frontend/) |
| PostgreSQL schema | [`data/sql/schema.sql`](../../data/sql/schema.sql) |
| GitHub Actions tests | [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) |

## Known documentation gaps

- The repository does not currently provide complete infrastructure-as-code for reproducible provisioning.
- Some JSON policy and workflow examples contain account-specific ARNs. Treat them as historical configuration references, not portable templates.
- The API proxy source contains the original API Gateway URL. Confirm the correct endpoint before any redeployment.
- The final state machine and its notification paths need fresh integration testing when AWS is reactivated.
- Screenshot and video evidence will be produced after the next development phase, not retroactively presented as October capstone evidence.

## After the demo

Disable scheduled reporting and CloudFront when appropriate; delete or stop chargeable resources only after checking dependencies and retaining any required snapshots. Verify billing afterwards. An S3 bucket, snapshot or log group may still incur storage charges even when compute is stopped.
