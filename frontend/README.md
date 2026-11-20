# FinTrust Dashboard

The FinTrust frontend is a **React + Vite** dashboard for the [FinTrust Transaction Insights and Risk Monitoring System](../README.md), an AWS-based, event-driven capstone prototype.

It provides a visual interface for reviewing transactions and risk classifications, monitoring CSV uploads, and accessing report information. The frontend was built for the completed October 2026 capstone. **The hosted AWS environment is currently shut down to control costs**, so this repository does not provide a live public demo.

## Dashboard sections

| Section | Purpose |
| --- | --- |
| **Overview** | Summary of transaction activity and risk insights |
| **Transactions** | Searchable, filterable, server-paginated transaction ledger with record details |
| **Risk monitoring** | Risk-focused transaction review and classifications |
| **Reports** | Access to report information provided by the backend |

### CSV upload and processing

The dashboard accepts a CSV upload and shows progress across six stages:

1. **File Received** — CSV uploaded and assigned an upload ID
2. **Processing Started** — AWS Step Functions begins ingestion
3. **Data Validation** — transaction rows are checked
4. **Transactions Queued** — valid rows enter SQS
5. **Risk Assessment** — risk rules are evaluated
6. **Results Saved** — transaction and risk results are persisted

The UI requests upload progress from the backend and displays processing, completion or failure states. The processing stages reflect backend tracking; they are not a local simulation.

## Technology

- React 19
- Vite 8
- JavaScript / JSX
- CSS
- Native `fetch` for API requests

The main application is [`src/App.jsx`](src/App.jsx), with styles in [`src/App.css`](src/App.css) and [`src/index.css`](src/index.css).

## Local development

**Requirements:** Node.js and npm compatible with the project's Vite version.

From the repository root:

```bash
cd frontend
npm install
npm run dev
```

Vite prints the local development URL in your terminal.

Additional commands:

```bash
npm run build
npm run preview
npm run lint
```

These commands build, preview and lint the frontend. They **do not** provision AWS infrastructure.

## Backend and API configuration

The application currently uses the relative API prefix:

```js
const API_BASE = '/api'
```

Requests therefore target routes such as:

- `GET /api/transactions`
- `GET /api/reports`
- `GET /api/health`
- `POST /api/upload`
- `GET /api/uploads/{upload_id}/progress`

A working backend, API routing or local reverse proxy is required for data-backed features. Running `npm run dev` alone starts the frontend but **does not automatically connect to the retired AWS deployment**. Before reconnecting to an AWS environment, review the current API proxy, credentials, access controls and route configuration.

## Architecture

The dashboard is the presentation layer. Transaction ingestion, validation, scoring, storage, notifications and reports are handled by the backend AWS services.

- [Final architecture diagram](../docs/architecture/fintrust-final-architecture.svg)
- [Architecture documentation](../docs/architecture/system-architecture.md)
- [Backend source](../backend/fintrust/)
- [Main project README](../README.md)

## Screenshots

Verified screenshots from the completed capstone have not yet been added to this README. Add screenshots of the Overview, Transactions, Risk Monitoring, Reports and CSV processing screens when suitable images are available. Avoid screenshots containing real credentials, account details or other sensitive information.

## Project status

This frontend is part of the **original completed capstone**, not a currently hosted production banking application. Future portfolio improvements should be documented separately from the features demonstrated in October 2026.
