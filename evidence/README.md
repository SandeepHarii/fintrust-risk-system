# FinTrust Capstone Evidence

This directory preserves screenshots from the **October 2026 capstone**. They are historical evidence, not proof that the AWS environment is currently active. The environment was shut down after the demonstration to manage costs.

## Evidence index

| Area | Evidence |
| --- | --- |
| S3, Lambda, validation, quarantine, RDS, DynamoDB and SQS | [Week 13, Day 4](week-13/day-4/) |
| API Gateway routes, API keys, usage plan and query responses | [Week 13, Day 5](week-13/day-5/) |
| Upload API, SQS, flag/resolve operations and SES alerts | [Week 14, Day 1](week-14/day-1/) |
| CloudWatch metrics, alarms, Logs Insights and X-Ray traces | [Week 14, Day 2](week-14/day-2/) |
| Unit tests, integration tests and pytest setup | [Week 14, Day 3](week-14/day-3/) |
| SQL reporting, report Lambda, S3 reports and EventBridge | [Week 14, Day 4](week-14/day-4/) |
| End-to-end pipeline and received SES risk notifications | [Week 14, Day 5](week-14/day-5/) |

### Selected evidence

- [E2E pipeline test result](week-14/day-5/W14D5_01_E2E_Pipeline_Passed.png)
- [Unit tests passing](week-14/day-3/W14D3_01_Unit_Tests_Passing.png)
- [Integration tests passing](week-14/day-3/W14D3_02_Integration_Tests_Passing.png)
- [CloudWatch custom metrics](week-14/day-2/W14-D2-01-CloudWatch-Custom-Metrics.png)
- [X-Ray successful trace](week-14/day-2/W14-D2-05-XRay-Successful-Trace.png)
- [S3 report objects](week-14/day-4/W14D4_06_S3_Report_Objects.png)

## Priority screenshot review

Before sharing this repository as a polished public portfolio, inspect the API-key-related screenshots in [Week 13, Day 5](week-13/day-5/), especially the API key association and successful request images. Confirm no **actual API key values**, authorization headers, email addresses or other secrets are visible. Screenshot filenames alone cannot establish whether values are exposed. If a genuine key is visible, revoke/rotate it in AWS before publishing a redacted replacement. Also inspect the SES email screenshots for personal contact details.

## Privacy and presentation

These screenshots were committed as part of the capstone evidence. **Review and redact any personal data, email addresses, credentials, tokens or sensitive account details before using them in a public portfolio or demo video.** Their presence in GitHub does not mean each image has passed a privacy review.

Frontend screenshots and a complete walkthrough video are intentionally deferred until the next development phase. Keep future enhancements separate from original capstone evidence.
