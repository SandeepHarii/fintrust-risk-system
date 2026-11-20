# FinTrust Repository Review

**Review date:** November 2026. **Scope:** Selected tracked source files, security plans, IAM examples, CI workflow, API documentation and project structure on `develop`. This is a targeted static review, **not** a full repository-history secret scan or live AWS security assessment.

## Findings

| Priority | Finding | Recommended action |
| --- | --- | --- |
| High before public deployment | API Gateway API keys and usage plans are not end-user authentication or authorization | Add an authorizer/identity solution and enforce per-user permissions |
| High before reactivation | The API proxy uses a hardcoded capstone API Gateway base URL | Configure the upstream URL through a controlled environment variable and validate it |
| Medium | Step Functions and IAM JSON examples contain account-specific ARNs | Parameterize or generate deployment-specific values; preserve historical examples until a tested replacement exists |
| Medium | The repository includes a simplified Step Functions workflow alongside the final notification-enabled workflow | Mark the simplified version as historical; final version is `fintrust-upload-workflow.json` |
| Medium | `docs/api/api-design.md` includes planned/illustrative contracts that may not match the deployed frontend proxy | Verify route, payload and response contracts against the actual API handlers before publishing them as definitive |
| Medium | The API proxy has a restricted route allowlist; `POST /flag` and `POST /resolve` are not in it | Check whether those operations are intended for the hosted frontend or only the backend API |
| Medium | `infrastructure/iam/lambda-vpc-policy.json` uses `Resource: "*"` for EC2 network-interface operations | Review IAM action-level resource scoping and applicable AWS managed-role guidance; a wildcard is not automatically a security flaw for every EC2 action |
| Medium | GitHub Actions uses long-lived AWS access key secrets for manual E2E testing | Prefer GitHub OIDC with a narrowly scoped AWS role when redeploying |
| Low | Existing `.gitignore` lacked some common local secret and IaC state patterns | Additional ignore patterns added; note that this does not protect previously committed files |
| Documentation | Security plan describes some requirements as if already verified | Added a status/limitations section to distinguish design intent from verified deployment state |

## Confirmed non-secret examples

AWS account IDs, Lambda ARNs, bucket names and API Gateway URLs are infrastructure identifiers, not credentials. Their presence alone does **not** demonstrate a secret leak. However, they make the examples account-specific and can reveal deployment details.

No actual AWS access key or database password was confirmed exposed in the inspected files. **This is not proof that the entire repository or Git history is free of secrets.**

## Follow-up before AWS reactivation

1. Run a repository and Git-history secret scan using a dedicated scanner, then investigate and rotate any genuine exposed credentials.
2. Verify IAM roles, S3 bucket policies, RDS security groups and API authorization against actual AWS resources.
3. Parameterize deployment values and replace hardcoded API endpoints.
4. Test the final upload workflow, notification idempotency and failure cases.
5. Review GitHub Actions credentials and move to OIDC where practical.
6. Run the test suites and record actual outcomes.

Do not delete historical capstone configurations merely to make the repository look cleaner. Keep the original submission distinguishable from later improvements.
