# FinTrust Testing and CI

This document describes the test suites and GitHub Actions configuration in the October 2026 capstone repository. It does not claim that every test passes today or that the retired AWS environment is available.

## Test suites

| Suite | Location | Dependency | Execution |
| --- | --- | --- | --- |
| Unit | [`tests/unit/`](../../tests/unit/) | Python dependencies and mocked services where applicable | Push, pull request and manual GitHub Actions runs |
| Integration | [`tests/integration/`](../../tests/integration/) | PostgreSQL database initialized from `data/sql/schema.sql` | Push to `develop` |
| End-to-end | [`tests/e2e/`](../../tests/e2e/) | Active AWS resources, API endpoint and credentials | Manually triggered GitHub Actions workflow |

Unit test files cover ingestion, scoring, alerts, DynamoDB, reporting, S3, validators, persistence and API/report behavior. The integration and end-to-end suites exercise broader system behavior.

## Run unit tests locally

From the repository root, using Python 3.13:

```bash
python -m venv .venv
# Activate .venv for your operating system
python -m pip install -r requirements.txt
python -m pytest tests/unit -v
```

`pytest.ini` sets `tests/unit` as the default test path, so explicit paths are recommended when running a particular suite.

## Run integration tests

Start a local PostgreSQL database, initialize it using [`data/sql/schema.sql`](../../data/sql/schema.sql), then set the required `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` and `DB_SSLMODE` environment variables.

```bash
python -m pytest tests/integration -v
```

The [CI workflow](../../.github/workflows/ci.yml) demonstrates the test database configuration using PostgreSQL 18. Its example `postgres` password is an ephemeral CI-only test credential, **not** a production secret.

## AWS end-to-end tests

```bash
python -m pytest tests/e2e -v -s
```

Run these tests only with an authorized, active AWS test environment, synthetic data and a valid API configuration. The GitHub Actions job requires `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and `FINTRUST_API_KEY` repository secrets. The workflow currently contains a capstone-specific API URL, which must be reviewed before reactivation.

## What CI does and does not do

- **Does:** run unit tests on pushes and pull requests; run PostgreSQL integration tests on pushes to `develop`; allow manually triggered AWS end-to-end tests.
- **Does not:** automatically deploy the complete AWS infrastructure; run live AWS end-to-end tests on every commit; guarantee that the hosted demo is available.

For the latest actual pass/fail status, inspect [GitHub Actions](https://github.com/SandeepHarii/fintrust-risk-system/actions) or run the suites. Do not use historical test counts as proof of current CI status.

## Evidence and future improvements

After reactivation, capture redacted test results, workflow runs, failure-path demonstrations and operational metrics. Keep original October capstone evidence separate from results of later portfolio-product enhancements.
