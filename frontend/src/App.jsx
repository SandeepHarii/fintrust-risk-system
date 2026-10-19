import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import './App.css'

const API_BASE = '/api'
const PAGE_SIZE = 5

/* ------------------------------------------------------------------
 * Navigation
 * ------------------------------------------------------------------ */

const navigation = [
  { key: 'overview', label: 'Overview', icon: '▦' },
  { key: 'transactions', label: 'Transactions', icon: '↔' },
  { key: 'risk', label: 'Risk monitoring', icon: '◈' },
  { key: 'reports', label: 'Reports', icon: '↧' },
]

/* ------------------------------------------------------------------
 * API layer
 * ------------------------------------------------------------------ */

async function apiRequest(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...(options.body && !options.headers?.['Content-Type']
        ? { 'Content-Type': 'application/json' }
        : {}),
      ...options.headers,
    },
  })

  const text = await response.text()
  let data

  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = text
  }

  if (!response.ok) {
    const message =
      data && typeof data === 'object'
        ? data.message || data.detail || data.error
        : null

    throw new Error(message || `Request failed (${response.status})`)
  }

  return data
}

/* ------------------------------------------------------------------
 * Helpers
 * ------------------------------------------------------------------ */

function getArray(data) {
  if (Array.isArray(data)) return data
  if (!data || typeof data !== 'object') return []

  for (const key of ['transactions', 'items', 'records', 'results', 'data']) {
    if (Array.isArray(data[key])) return data[key]
  }

  return []
}

function toNumber(value) {
  if (value === null || value === undefined || value === '') return null

  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

function formatNumber(value) {
  const n = toNumber(value)
  return n === null ? '—' : n.toLocaleString('en-ZA')
}

function formatCurrency(value, currency = 'ZAR') {
  const n = toNumber(value)
  if (n === null) return '—'

  try {
    return n.toLocaleString('en-ZA', {
      style: 'currency',
      currency: currency || 'ZAR',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })
  } catch {
    return `${currency || 'ZAR'} ${n.toFixed(2)}`
  }
}

function formatCompactCurrency(value) {
  const n = toNumber(value)
  if (n === null) return '—'

  const abs = Math.abs(n)

  if (abs >= 1_000_000) return `R ${(n / 1_000_000).toFixed(1)}M`
  if (abs >= 1_000) return `R ${(n / 1_000).toFixed(1)}K`

  return `R ${n.toFixed(0)}`
}

function formatDate(value) {
  if (!value) return '—'

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)

  return date.toLocaleString('en-ZA', {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

function formatDay(value) {
  if (!value) return '—'

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)

  return date.toLocaleDateString('en-ZA', {
    month: 'short',
    day: '2-digit',
  })
}

function formatDateShort(value) {
  if (!value) return '—'

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)

  return date.toLocaleDateString('en-ZA', {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
  })
}

function formatFileSize(bytes) {
  const size = Number(bytes)

  if (!Number.isFinite(size) || size < 0) return '—'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`

  return `${(size / (1024 * 1024)).toFixed(2)} MB`
}

function formatReportMonth(period) {
  if (!period || !/^\d{4}-\d{2}$/.test(period)) {
    return period ?? '—'
  }

  const date = new Date(`${period}-01T00:00:00`)

  if (Number.isNaN(date.getTime())) return period

  return date.toLocaleDateString('en-ZA', {
    year: 'numeric',
    month: 'long',
  })
}

function formatPercent(value, total) {
  if (!total || total <= 0) return '—'
  return `${((value / total) * 100).toFixed(1)}%`
}

function getTransactionId(t, i = 0) {
  return t?.transaction_id ?? `Record ${i + 1}`
}

function getRisk(t) {
  const raw = String(t?.risk_flag ?? '').toUpperCase()

  if (raw === 'HIGH') return 'High'
  if (raw === 'MEDIUM') return 'Medium'
  if (raw === 'LOW') return 'Low'

  return null
}

function getRiskLabel(t) {
  return getRisk(t) ?? 'Unclassified'
}

function getTransactionFlags(t) {
  if (Array.isArray(t?.flags) && t.flags.length > 0) {
    return t.flags.filter(Boolean).map((f) => String(f).toUpperCase())
  }

  const out = []
  const amount = toNumber(t?.amount)

  if (amount !== null && amount > 50_000) out.push('HIGH_AMOUNT')

  if (
    t?.source_country &&
    t?.destination_country &&
    t.source_country !== t.destination_country
  ) {
    out.push('CROSS_BORDER')
  }

  return out
}

/* ------------------------------------------------------------------
 * Small shared UI
 * ------------------------------------------------------------------ */

function StatusDot({ status = 'default' }) {
  return <span className={`status-dot ${status}`} aria-hidden="true" />
}

function SectionHeading({ title, subtitle, right, eyebrow }) {
  return (
    <div className="section-heading">
      <div>
        {eyebrow && <p className="section-eyebrow">{eyebrow}</p>}
        <h2>{title}</h2>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {right}
    </div>
  )
}

function Empty({ title, body }) {
  return (
    <div className="empty">
      <strong>{title}</strong>
      <p>{body}</p>
    </div>
  )
}

/**
 * Shared server-paginated transaction table.
 * Used by both the Transactions ledger and the Risk review queue so the
 * two screens stay visually and behaviourally consistent.
 */
function TransactionTable({
  transactions,
  pagination,
  loading,
  error,
  emptyMessage,
  onSelect,
  onPageChange,
}) {
  const total = Number(pagination?.total ?? 0)
  const totalPages = Math.max(1, Number(pagination?.total_pages ?? 1))
  const safePage = Number(pagination?.page ?? 1)
  const pageSize = Number(pagination?.page_size ?? PAGE_SIZE)

  const startIndex = total === 0 ? 0 : (safePage - 1) * pageSize
  const endIndex = Math.min(startIndex + transactions.length, total)

  const canPrev = safePage > 1
  const canNext = safePage < totalPages

  return (
    <>
      <div className="table-wrap">
        <table className="txn-table">
          <colgroup>
            <col className="col-risk" />
            <col className="col-txn" />
            <col className="col-account" />
            <col className="col-amount" />
            <col className="col-flags" />
            <col className="col-date" />
          </colgroup>

          <thead>
            <tr>
              <th scope="col">Risk</th>
              <th scope="col">Transaction</th>
              <th scope="col">Account</th>
              <th scope="col" className="right">
                Amount
              </th>
              <th scope="col">Flag</th>
              <th scope="col" className="right">
                Date
              </th>
            </tr>
          </thead>

          <tbody>
            {loading && transactions.length === 0 && (
              <tr>
                <td colSpan={6} className="empty-row">
                  Loading transactions…
                </td>
              </tr>
            )}

            {!loading && error && (
              <tr>
                <td colSpan={6} className="empty-row">
                  Unable to load transactions: {error}
                </td>
              </tr>
            )}

            {!loading && !error && transactions.length === 0 && (
              <tr>
                <td colSpan={6} className="empty-row">
                  {emptyMessage ?? 'No transactions match the current filter.'}
                </td>
              </tr>
            )}

            {transactions.map((t, index) => {
              const globalIndex = startIndex + index
              const risk = getRiskLabel(t)
              const id = getTransactionId(t, globalIndex)

              const shortId =
                typeof id === 'string' ? id.replace(/^TXN-?/i, '') : id

              const flags = getTransactionFlags(t)
              const dateValue = t.tx_date ?? t.created_at

              return (
                <tr
                  key={String(id)}
                  className={`row-${risk.toLowerCase()}`}
                  onClick={() => onSelect(t)}
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      onSelect(t)
                    }
                  }}
                >
                  <td>
                    <span className={`risk-badge ${risk.toLowerCase()}`}>
                      <span className="badge-dot" />
                      {risk}
                    </span>
                  </td>

                  <td>
                    <strong className="mono txn-id">#{shortId}</strong>
                  </td>

                  <td>
                    <span className="mono account-mask">
                      {t.account_id ?? '—'}
                    </span>
                  </td>

                  <td className="amount right">
                    {formatCurrency(t.amount, t.currency)}
                  </td>

                  <td>
                    {flags.length === 0 ? (
                      <span className="muted">—</span>
                    ) : (
                      <span className="flag-stack">
                        {flags.map((f) => (
                          <span className="flag-pill" key={f}>
                            {f}
                          </span>
                        ))}
                      </span>
                    )}
                  </td>

                  <td className="right muted">
                    <span className="date-cell">
                      {formatDateShort(dateValue)}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="pagination">
        <span className="pagination-info">
          {loading
            ? 'Loading…'
            : total === 0
              ? 'No records'
              : `Showing ${startIndex + 1}–${endIndex} of ${total}`}
        </span>

        <div className="pagination-controls">
          <button
            className="pagination-button"
            type="button"
            onClick={() => onPageChange(safePage - 1)}
            disabled={!canPrev || loading}
            aria-label="Previous page"
          >
            ← Prev
          </button>

          <span className="pagination-page mono">
            Page {safePage} of {totalPages}
          </span>

          <button
            className="pagination-button"
            type="button"
            onClick={() => onPageChange(safePage + 1)}
            disabled={!canNext || loading}
            aria-label="Next page"
          >
            Next →
          </button>
        </div>
      </div>
    </>
  )
}

/* ==================================================================
 * ==================================================================
 * ==                                                              ==
 * ==                  CSV PROCESSING SECTION                      ==
 * ==                                                              ==
 * ==================================================================
 * ================================================================== */

const PROCESSING_STAGES = [
  {
    key: 'received',
    apiKey: 'csv_uploaded',
    title: 'File Received',
    description: 'CSV uploaded to Amazon S3 and assigned an upload ID.',
  },
  {
    key: 'started',
    apiKey: 'ingestion_started',
    title: 'Processing Started',
    description: 'AWS Step Functions has started the ingestion workflow.',
  },
  {
    key: 'validation',
    apiKey: 'validation',
    title: 'Data Validation',
    description:
      'Records are checked for valid formats, required fields and data quality.',
  },
  {
    key: 'queued',
    apiKey: 'transactions_queued',
    title: 'Transactions Queued',
    description: 'Valid records are added to Amazon SQS for processing.',
  },
  {
    key: 'risk',
    apiKey: 'risk_scoring',
    title: 'Risk Assessment',
    description:
      "Transactions are evaluated against FinTrust's risk detection rules.",
  },
  {
    key: 'saved',
    apiKey: 'results_persisted',
    title: 'Results Saved',
    description:
      'Processed transactions and risk results are saved to the database.',
  },
]

function ToastNotification({ toast, onDismiss }) {
  if (!toast) return null

  return (
    <div
      className={`upload-toast ${toast.type || 'success'}`}
      role={toast.type === 'error' ? 'alert' : 'status'}
      aria-live="polite"
    >
      <div className="toast-icon" aria-hidden="true">
        {toast.type === 'error' ? '!' : '✓'}
      </div>

      <div className="toast-content">
        <strong>{toast.title}</strong>
        <span>{toast.message}</span>
      </div>

      <button
        className="toast-close"
        type="button"
        aria-label="Dismiss notification"
        onClick={onDismiss}
      >
        ×
      </button>
    </div>
  )
}

function ProcessingScreen({
  uploadId,
  fileName,
  progress,
  progressError,
  onUploadAnother,
}) {
  const status = String(progress?.status ?? 'PROCESSING').toUpperCase()
  const isCompleted = status === 'COMPLETED'
  const isFailed = status === 'FAILED'

  const stageStatuses = progress?.stages ?? {}

  const completedCount = PROCESSING_STAGES.filter(
    (stage) =>
      String(stageStatuses[stage.apiKey] ?? '').toUpperCase() === 'COMPLETED',
  ).length

  const overallProgress = isCompleted
    ? 100
    : Math.round((completedCount / PROCESSING_STAGES.length) * 100)

  const currentStageKey = progress?.current_stage

  const activeStage = PROCESSING_STAGES.find(
    (stage) => stage.apiKey === currentStageKey,
  )

  const activeStageTitle = isCompleted
    ? 'Processing Complete'
    : activeStage?.title ?? 'Awaiting progress'

  function getStageState(stage) {
    const stageStatus = String(
      stageStatuses[stage.apiKey] ?? '',
    ).toUpperCase()

    if (stageStatus === 'COMPLETED') return 'completed'
    if (stageStatus === 'IN_PROGRESS') return 'active'
    if (stageStatus === 'FAILED') return 'failed'

    if (isFailed && stage.apiKey === currentStageKey) {
      return 'failed'
    }

    return 'pending'
  }

  function getStageStatusLabel(stage) {
    const state = getStageState(stage)

    if (state === 'completed') return 'Completed'
    if (state === 'active') return 'In Progress'
    if (state === 'failed') return 'Failed'

    return 'Pending'
  }

  const statusLabel = isCompleted
    ? 'Completed'
    : isFailed
      ? 'Failed'
      : 'Processing'

  const statusDot = isCompleted
    ? 'online'
    : isFailed
      ? 'offline'
      : 'default'

  return (
    <div className="upload-preview">
      <section className="content-card upload-card">
        <div className="section-heading upload-header">
          <div>
            <p className="section-eyebrow">TRANSACTION INGESTION</p>
            <h2>CSV Processing</h2>
            <p>
              Your file is being processed through the FinTrust risk
              monitoring pipeline.
            </p>
          </div>

          <span className="upload-status">
            <StatusDot status={statusDot} />
            {statusLabel}
          </span>
        </div>

        <div className="upload-details">
          <div className="detail-item">
            <span className="detail-label">UPLOAD ID</span>
            <strong className="mono">{uploadId}</strong>
          </div>

          <div className="detail-item">
            <span className="detail-label">FILE NAME</span>
            <strong>{fileName}</strong>
          </div>

          <div className="detail-item">
            <span className="detail-label">CURRENT STAGE</span>
            <strong>{activeStageTitle}</strong>
          </div>
        </div>

        <div className="upload-progress-section">
          <div className="progress-heading">
            <div>
              <h3>Overall Progress</h3>
              <p>
                {completedCount} of {PROCESSING_STAGES.length} stages completed
              </p>
            </div>

            <strong className="progress-percentage">
              {overallProgress}%
            </strong>
          </div>

          <div className="upload-progress">
            <div
              className="upload-progress-fill"
              style={{ width: `${overallProgress}%` }}
            />
          </div>

          <div className="progress-footer">
            <span>
              {isCompleted
                ? 'All processing stages completed'
                : isFailed
                  ? 'Processing failed'
                  : 'Processing your transactions'}
            </span>

            <span>
              {completedCount} / {PROCESSING_STAGES.length} stages
            </span>
          </div>
        </div>

        <div className="upload-stages-section">
          <div className="upload-section-heading">
            <h3>Processing Stages</h3>
            <span>
              {completedCount} of {PROCESSING_STAGES.length} completed
            </span>
          </div>

          <div className="stepper">
            {PROCESSING_STAGES.map((stage, index) => {
              const state = getStageState(stage)
              const position = index + 1
              const isLast = index === PROCESSING_STAGES.length - 1

              return (
                <div key={stage.key} className={`stepper-step ${state}`}>
                  <span className="stepper-status">
                    {getStageStatusLabel(stage)}
                  </span>

                  <div className="stepper-track">
                    <div className="stepper-indicator" aria-hidden="true">
                      {state === 'completed' ? '✓' : position}
                    </div>

                    {!isLast && <div className="stepper-line" />}
                  </div>

                  <div className="stepper-copy">
                    <span className="stepper-title">{stage.title}</span>
                    <p className="stepper-desc">{stage.description}</p>
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        <div className="upload-summary-section">
          <div className="upload-section-heading">
            <h3>Processing Summary</h3>
            <span>Current results</span>
          </div>

          <div className="upload-summary-grid">
            <div className="upload-summary-item">
              <span>TOTAL RECORDS</span>
              <strong>{formatNumber(progress?.total_records)}</strong>
            </div>

            <div className="upload-summary-item valid">
              <span>VALID RECORDS</span>
              <strong>{formatNumber(progress?.valid_records)}</strong>
            </div>

            <div className="upload-summary-item quarantined">
              <span>QUARANTINED</span>
              <strong>{formatNumber(progress?.quarantined_records)}</strong>
            </div>
          </div>
        </div>

        {isFailed && progress?.failure_reason && (
          <div className="upload-banner" role="alert">
            <StatusDot status="offline" />
            <span>Processing failed: {progress.failure_reason}</span>
          </div>
        )}

        {progressError && !isCompleted && !isFailed && (
          <div className="upload-banner" role="status">
            <StatusDot status="default" />
            <span>
              Unable to refresh progress: {progressError}. Retrying
              automatically.
            </span>
          </div>
        )}

        <div className="upload-card-footer">
          <div className="refresh-indicator">
            <StatusDot status={statusDot} />
            {isCompleted
              ? 'Processing finished'
              : isFailed
                ? 'Processing stopped'
                : 'Live updates · checking every second'}
          </div>

          {isCompleted || isFailed ? (
            <button
              className="primary-button"
              type="button"
              onClick={onUploadAnother}
            >
              ↑ Upload another file
            </button>
          ) : (
            <span>FinTrust Transaction Monitoring</span>
          )}
        </div>
      </section>
    </div>
  )
}

/* ==================================================================
 * ==               END OF CSV PROCESSING SECTION                  ==
 * ================================================================== */

function DropZone({ onFile, uploading, uploadMessage }) {
  const [hover, setHover] = useState(false)
  const inputRef = useRef(null)

  function handleClick() {
    if (uploading) return
    inputRef.current?.click()
  }

  function handleChange(e) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (file) onFile(file)
  }

  function handleDragOver(e) {
    e.preventDefault()
    e.stopPropagation()
    if (uploading) return
    setHover(true)
  }

  function handleDragLeave(e) {
    e.preventDefault()
    e.stopPropagation()
    setHover(false)
  }

  function handleDrop(e) {
    e.preventDefault()
    e.stopPropagation()
    setHover(false)

    if (uploading) return

    const file = e.dataTransfer?.files?.[0]
    if (file) onFile(file)
  }

  return (
    <section className="content-card" id="upload">
      <SectionHeading
        eyebrow="POST /upload"
        title="Upload transaction CSV"
        subtitle="Drop a CSV file into the zone below, or click to browse. The file is sent to the ingest Lambda and processed asynchronously."
      />

      <div className="dropzone-wrap">
        <div
          className={`dropzone ${hover ? 'hover' : ''} ${uploading ? 'busy' : ''}`}
          onClick={handleClick}
          onDragOver={handleDragOver}
          onDragEnter={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          role="button"
          tabIndex={0}
          aria-label="Upload a transaction CSV file"
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              handleClick()
            }
          }}
        >
          <div className="dropzone-icon" aria-hidden="true">
            ↥
          </div>

          <strong className="dropzone-title">
            {uploading ? 'Uploading…' : 'Drop your CSV here'}
          </strong>

          <span className="dropzone-sub">
            {uploading
              ? 'Sending the file to the ingest Lambda'
              : 'or click to browse — only .csv files are accepted'}
          </span>

          <span className="dropzone-meta">
            CSV only · rows are validated on ingest, invalid rows are
            quarantined to a separate S3 bucket
          </span>

          <input
            ref={inputRef}
            type="file"
            accept=".csv,text/csv"
            onChange={handleChange}
            hidden
            disabled={uploading}
          />
        </div>

        {uploadMessage && (
          <div className="upload-banner" role="status" aria-live="polite">
            <StatusDot status={uploading ? 'default' : 'online'} />
            <span>{uploadMessage}</span>
          </div>
        )}
      </div>
    </section>
  )
}

function BackToTop() {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    function onScroll() {
      setVisible(window.scrollY > 300)
    }

    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })

    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  function scrollTop() {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  if (!visible) return null

  return (
    <button
      className="back-to-top"
      type="button"
      onClick={scrollTop}
      aria-label="Back to top"
      title="Back to top"
    >
      ↑
    </button>
  )
}

function DetailDrawer({ transaction, onClose }) {
  const open = Boolean(transaction)

  useEffect(() => {
    if (!open) return

    function onKey(event) {
      if (event.key === 'Escape') onClose()
    }

    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  const risk = getRiskLabel(transaction)
  const flags = getTransactionFlags(transaction)

  const fields = [
    { label: 'Transaction ID', value: transaction.transaction_id, mono: true },
    { label: 'Account', value: transaction.account_id, mono: true },
    {
      label: 'Amount',
      value: formatCurrency(transaction.amount, transaction.currency),
      mono: true,
    },
    { label: 'Currency', value: transaction.currency },
    { label: 'Type', value: transaction.transaction_type },
    { label: 'Transaction date', value: formatDate(transaction.tx_date) },
    { label: 'Created at', value: formatDate(transaction.created_at) },
    { label: 'Source country', value: transaction.source_country, mono: true },
    {
      label: 'Destination country',
      value: transaction.destination_country,
      mono: true,
    },
  ]

  return (
    <div className="drawer-backdrop" onClick={onClose} role="presentation">
      <aside
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-label="Transaction detail"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="drawer-header">
          <div>
            <p className="section-eyebrow">TRANSACTION DETAIL</p>
            <h2 className="mono">#{transaction.transaction_id ?? '—'}</h2>

            <div className="drawer-tags">
              <span className={`risk-badge ${risk.toLowerCase()}`}>
                <span className="badge-dot" />
                {risk}
              </span>

              {flags.map((f) => (
                <span className="flag-pill" key={f}>
                  {f}
                </span>
              ))}
            </div>
          </div>

          <button
            className="drawer-close"
            type="button"
            onClick={onClose}
            aria-label="Close detail panel"
          >
            ✕
          </button>
        </header>

        <div className="drawer-body">
          <dl className="detail-list">
            {fields.map((f) => (
              <div className="detail-row" key={f.label}>
                <dt>{f.label}</dt>
                <dd className={f.mono ? 'mono' : undefined}>
                  {f.value ?? '—'}
                </dd>
              </div>
            ))}
          </dl>

          <div className="drawer-actions">
            <button
              className="secondary-button"
              type="button"
              onClick={onClose}
            >
              Close
            </button>

            <button
              className="primary-button"
              type="button"
              disabled
              title="Coming in a future iteration"
            >
              Flag for review
            </button>
          </div>
        </div>
      </aside>
    </div>
  )
}

function Sidebar({ activePage, onNavigate, apiStatus }) {
  return (
    <aside className="sidebar">
      <a
        className="brand"
        href="#overview"
        onClick={(e) => {
          e.preventDefault()
          onNavigate('overview')
        }}
        aria-label="FinTrust home"
      >
        <div className="brand-mark">F</div>

        <div className="brand-copy">
          <strong>FinTrust</strong>
          <span>RISK &amp; INSIGHTS</span>
        </div>
      </a>

      <div className="sidebar-section">
        <p className="nav-label">WORKSPACE</p>

        <nav className="main-navigation" aria-label="Main navigation">
          {navigation.map((item) => (
            <button
              type="button"
              key={item.key}
              className={`nav-item ${activePage === item.key ? 'active' : ''}`}
              onClick={() => onNavigate(item.key)}
            >
              <span className="nav-icon" aria-hidden="true">
                {item.icon}
              </span>
              <span>{item.label}</span>
            </button>
          ))}
        </nav>
      </div>

      <div className="sidebar-bottom">
        <div className="sidebar-status">
          <StatusDot
            status={
              apiStatus === 'online'
                ? 'online'
                : apiStatus === 'offline'
                  ? 'offline'
                  : 'default'
            }
          />

          <span>
            {apiStatus === 'online'
              ? 'API connected'
              : apiStatus === 'offline'
                ? 'API unavailable'
                : 'Connecting to API'}
          </span>
        </div>

        <div className="profile">
          <div className="avatar">FT</div>

          <div className="profile-copy">
            <strong>FinTrust Compliance</strong>
            <span>Operations team</span>
          </div>
        </div>
      </div>
    </aside>
  )
}

function RefreshIcon({ spinning }) {
  return (
    <span
      className={`refresh-icon ${spinning ? 'spinning' : ''}`}
      aria-hidden="true"
    >
      ↻
    </span>
  )
}

function Topbar({
  activePage,
  apiStatus,
  onRefresh,
  loading,
  theme,
  onToggleTheme,
}) {
  const crumb =
    navigation.find((n) => n.key === activePage)?.label ?? 'Overview'

  return (
    <header className="topbar">
      <div className="breadcrumb">
        FinTrust <span>/</span> <strong>{crumb}</strong>
      </div>

      <div className="topbar-right">
        <span className="environment">
          <StatusDot
            status={
              apiStatus === 'online'
                ? 'online'
                : apiStatus === 'offline'
                  ? 'offline'
                  : 'default'
            }
          />

          {apiStatus === 'online'
            ? 'Connected'
            : apiStatus === 'offline'
              ? 'Disconnected'
              : 'Checking status'}
        </span>

        <button
          className="refresh-button"
          type="button"
          onClick={onRefresh}
          disabled={loading}
          aria-label="Refresh data"
          title="Refresh data"
        >
          <RefreshIcon spinning={loading} />
        </button>

        <button
          className={`theme-toggle ${theme === 'new' ? 'is-new' : 'is-classic'}`}
          type="button"
          role="switch"
          aria-checked={theme === 'new'}
          aria-label={`Switch to ${theme === 'new' ? 'Light Mode' : 'Dark Mode'}`}
          title={`Switch to ${theme === 'new' ? 'Light Mode' : 'Dark Mode'}`}
          onClick={onToggleTheme}
        >
          <span className="theme-toggle-label">
            {theme === 'new' ? 'Dark Mode' : 'Light Mode'}
          </span>

          <span className="theme-toggle-track" aria-hidden="true">
            <span className="theme-toggle-thumb" />
          </span>
        </button>
      </div>
    </header>
  )
}

function SummaryCards({ transactions, insights, loading }) {
  const insightTx =
    insights?.transactions && typeof insights.transactions === 'object'
      ? insights.transactions
      : {}

  const counts = useMemo(() => {
    return transactions.reduce(
      (acc, t) => {
        const r = getRisk(t)

        if (r === 'High') acc.high += 1
        else if (r === 'Medium') acc.medium += 1
        else if (r === 'Low') acc.low += 1

        return acc
      },
      { high: 0, medium: 0, low: 0 },
    )
  }, [transactions])

  const cards = [
    {
      label: 'Total transactions',
      value: formatNumber(insightTx.total ?? transactions.length),
      note: 'Records in the ledger',
      icon: '↔',
      color: 'blue',
    },
    {
      label: 'High-risk transactions',
      value: formatNumber(insightTx.high ?? counts.high),
      note: 'Require priority review',
      icon: '!',
      color: 'red',
    },
    {
      label: 'Medium-risk transactions',
      value: formatNumber(insightTx.medium ?? counts.medium),
      note: 'Flagged for investigation',
      icon: '◈',
      color: 'amber',
    },
    {
      label: 'Low-risk transactions',
      value: formatNumber(insightTx.low ?? counts.low),
      note: 'Routine activity, no action needed',
      icon: '✓',
      color: 'green',
    },
  ]

  return (
    <section className="summary-grid" aria-label="Transaction summary">
      {cards.map((card) => (
        <article className="summary-card" key={card.label}>
          <div className="summary-card-top">
            <p>{card.label}</p>
            <span className={`summary-icon ${card.color}`} aria-hidden="true">
              {card.icon}
            </span>
          </div>

          <h2>{loading ? '…' : card.value}</h2>
          <p className="summary-note">{card.note}</p>
        </article>
      ))}
    </section>
  )
}

function RiskDonut({ counts }) {
  const total = counts.high + counts.medium + counts.low

  if (total === 0) {
    return (
      <Empty
        title="No risk data"
        body="Upload a CSV or refresh to populate the risk mix."
      />
    )
  }

  const highPct = (counts.high / total) * 100
  const medPct = (counts.medium / total) * 100
  const lowPct = (counts.low / total) * 100

  const a1 = highPct
  const a2 = a1 + medPct

  const gradient = `conic-gradient(
    #FF6B6B 0 ${a1}%,
    #F0B849 ${a1}% ${a2}%,
    #3ECFA5 ${a2}% ${a2 + lowPct}%
  )`

  return (
    <div className="donut-wrap">
      <div
        className="donut"
        style={{ background: gradient }}
        role="img"
        aria-label={`Risk mix: ${counts.high} high, ${counts.medium} medium, ${counts.low} low`}
      >
        <div className="donut-hole">
          <strong>{formatNumber(total)}</strong>
          <span>records</span>
        </div>
      </div>

      <ul className="donut-legend">
        <li>
          <i className="dot high" /> High · {counts.high}
        </li>
        <li>
          <i className="dot medium" /> Medium · {counts.medium}
        </li>
        <li>
          <i className="dot low" /> Low · {counts.low}
        </li>
      </ul>
    </div>
  )
}

function DailyVolume({ transactions }) {
  const data = useMemo(() => {
    const buckets = new Map()

    transactions.forEach((t) => {
      const raw = t.tx_date ?? t.created_at
      if (!raw) return

      const d = new Date(raw)
      if (Number.isNaN(d.getTime())) return

      const key = d.toISOString().slice(0, 10)
      const entry = buckets.get(key) ?? { date: key, count: 0 }

      entry.count += 1
      buckets.set(key, entry)
    })

    return Array.from(buckets.values())
      .sort((a, b) => a.date.localeCompare(b.date))
      .slice(-14)
  }, [transactions])

  if (data.length === 0) {
    return (
      <Empty
        title="No volume yet"
        body="Records with a tx_date will populate this chart."
      />
    )
  }

  const max = Math.max(...data.map((d) => d.count))

  return (
    <div className="bars" role="img" aria-label="Daily transaction volume">
      {data.map((d) => (
        <div className="bar-col" key={d.date}>
          <div className="bar-track">
            <div
              className="bar-fill"
              style={{ height: `${(d.count / max) * 100}%` }}
              title={`${d.count} on ${d.date}`}
            />
          </div>

          <span className="bar-label">{formatDay(d.date)}</span>
        </div>
      ))}
    </div>
  )
}

function OverviewScreen({ transactions, insights, loading }) {
  const counts = useMemo(() => {
    return transactions.reduce(
      (acc, t) => {
        const r = getRisk(t)

        if (r === 'High') acc.high += 1
        else if (r === 'Medium') acc.medium += 1
        else if (r === 'Low') acc.low += 1

        return acc
      },
      { high: 0, medium: 0, low: 0 },
    )
  }, [transactions])

  const insightTx =
    insights?.transactions && typeof insights.transactions === 'object'
      ? insights.transactions
      : {}

  const merged = {
    high: insightTx.high ?? counts.high,
    medium: insightTx.medium ?? counts.medium,
    low: insightTx.low ?? counts.low,
  }

  return (
    <>
      <SummaryCards
        transactions={transactions}
        insights={insights}
        loading={loading}
      />

      <section className="charts-grid">
        <article className="content-card chart-card">
          <SectionHeading
            eyebrow="GET /insights"
            title="Risk mix"
            subtitle="Distribution of HIGH, MEDIUM and LOW records."
            right={
              <span className="live-label">
                <StatusDot status="online" /> Live
              </span>
            }
          />

          <div className="chart-body">
            {loading ? (
              <Empty title="Loading…" body="Fetching risk mix." />
            ) : (
              <RiskDonut counts={merged} />
            )}
          </div>
        </article>

        <article className="content-card chart-card wide">
          <SectionHeading
            eyebrow="tx_date · last 14 days"
            title="Daily transaction volume"
            subtitle="Number of records persisted per day."
          />

          <div className="chart-body">
            {loading ? (
              <Empty title="Loading…" body="Fetching volume." />
            ) : (
              <DailyVolume transactions={transactions} />
            )}
          </div>
        </article>
      </section>
    </>
  )
}

/* ------------------------------------------------------------------
 * Transactions
 * ------------------------------------------------------------------ */

const RISK_FILTERS = ['All', 'High', 'Medium', 'Low']
const FLAG_FILTERS = ['All', 'HIGH_AMOUNT', 'HIGH_VELOCITY', 'CROSS_BORDER']

function TransactionsScreen({
  transactions,
  pagination,
  loading,
  ledgerError,
  onFetch,
  onSelect,
  onFile,
  uploading,
  uploadMessage,
  processingJob,
  onUploadAnother,
}) {
  const [search, setSearch] = useState('')
  const [riskFilter, setRiskFilter] = useState('All')
  const [flagFilter, setFlagFilter] = useState('All')
  const [page, setPage] = useState(1)

  const hasActiveFilters =
    search.trim() !== '' || riskFilter !== 'All' || flagFilter !== 'All'

  useEffect(() => {
    onFetch({
      page,
      search,
      riskFilter,
      flagFilter,
    })
  }, [page, search, riskFilter, flagFilter, onFetch])

  function updateSearch(value) {
    setSearch(value)
    setPage(1)
  }

  function updateRiskFilter(value) {
    setRiskFilter(value)
    setPage(1)
  }

  function updateFlagFilter(value) {
    setFlagFilter(value)
    setPage(1)
  }

  function clearFilters() {
    setSearch('')
    setRiskFilter('All')
    setFlagFilter('All')
    setPage(1)
  }

  const total = Number(pagination?.total ?? 0)

  return (
    <>
      {processingJob ? (
        <ProcessingScreen
          uploadId={processingJob.uploadId}
          fileName={processingJob.fileName}
          progress={processingJob.progress}
          progressError={processingJob.progressError}
          onUploadAnother={onUploadAnother}
        />
      ) : (
        <DropZone
          onFile={onFile}
          uploading={uploading}
          uploadMessage={uploadMessage}
        />
      )}

      <section className="content-card filter-card">
        <SectionHeading
          eyebrow="QUERY FILTERS"
          title="Filters"
          subtitle="Combine search, risk and flag filters to narrow the ledger."
        />

        <div className="filter-body">
          <div className="filter-search">
            <label className="filter-search-label" htmlFor="txn-search">
              Search
            </label>

            <input
              id="txn-search"
              className="search-input"
              type="search"
              placeholder="ID, account, amount, flag…"
              value={search}
              onChange={(e) => updateSearch(e.target.value)}
            />
          </div>

          <div className="filter-options">
            <div className="filter-group">
              <span className="filter-group-label">Risk</span>

              <div
                className="filter-chips"
                role="tablist"
                aria-label="Risk filter"
              >
                {RISK_FILTERS.map((level) => (
                  <button
                    key={level}
                    role="tab"
                    aria-selected={riskFilter === level}
                    type="button"
                    className={`chip ${riskFilter === level ? 'active' : ''} ${level.toLowerCase()}`}
                    onClick={() => updateRiskFilter(level)}
                  >
                    {level}
                  </button>
                ))}
              </div>
            </div>

            <div className="filter-group">
              <span className="filter-group-label">Flag</span>

              <div
                className="filter-chips"
                role="tablist"
                aria-label="Flag filter"
              >
                {FLAG_FILTERS.map((flag) => (
                  <button
                    key={flag}
                    role="tab"
                    aria-selected={flagFilter === flag}
                    type="button"
                    className={`chip flag-chip ${flagFilter === flag ? 'active' : ''}`}
                    onClick={() => updateFlagFilter(flag)}
                  >
                    {flag}
                  </button>
                ))}
              </div>
            </div>

            <div className="filter-clear-row">
              <button
                className="clear-button"
                type="button"
                onClick={clearFilters}
                disabled={!hasActiveFilters}
                aria-label="Clear all filters"
              >
                ✕ Clear filters
              </button>
            </div>
          </div>
        </div>
      </section>

      <section className="content-card" id="transactions">
        <SectionHeading
          eyebrow="GET /transactions"
          title="Transaction ledger"
          subtitle="Live records from the RDS ledger. Click any row for the full record."
          right={
            <span className="table-count">
              {loading
                ? 'Loading…'
                : `${total} record${total === 1 ? '' : 's'}`}
            </span>
          }
        />

        <TransactionTable
          transactions={transactions}
          pagination={pagination}
          loading={loading}
          error={ledgerError}
          emptyMessage="No transactions match the current filter."
          onSelect={onSelect}
          onPageChange={setPage}
        />
      </section>
    </>
  )
}

/* ------------------------------------------------------------------
 * Risk overview (dedicated Risk monitoring page)
 * ------------------------------------------------------------------ */

function RiskLevelCard({ level, count, total, description }) {
  return (
    <article className={`risk-level-card ${level}`}>
      <div className="risk-level-card-top">
        <span className={`risk-badge ${level}`}>
          <span className="badge-dot" />
          {level === 'high' ? 'High' : level === 'medium' ? 'Medium' : 'Low'}
        </span>

        <span className="risk-level-share">{formatPercent(count, total)}</span>
      </div>

      <h3>{formatNumber(count)}</h3>
      <p className="risk-level-desc">{description}</p>
    </article>
  )
}

function RiskOverviewScreen({
  transactions,
  insights,
  loading,
  onSelect,
  refreshSignal,
}) {
  const insightTx =
    insights?.transactions && typeof insights.transactions === 'object'
      ? insights.transactions
      : {}

  const loadedCounts = useMemo(() => {
    return transactions.reduce(
      (acc, t) => {
        const r = getRisk(t)

        if (r === 'High') acc.high += 1
        else if (r === 'Medium') acc.medium += 1
        else if (r === 'Low') acc.low += 1

        return acc
      },
      { high: 0, medium: 0, low: 0 },
    )
  }, [transactions])

  const high = insightTx.high ?? loadedCounts.high
  const medium = insightTx.medium ?? loadedCounts.medium
  const low = insightTx.low ?? loadedCounts.low
  const total = high + medium + low

  const needsReview = high + medium

  const pct = (n) => (total === 0 ? 0 : (n / total) * 100)

  const segments = [
    { key: 'high', label: 'High', value: high },
    { key: 'medium', label: 'Medium', value: medium },
    { key: 'low', label: 'Low', value: low },
  ]

  const [queuePage, setQueuePage] = useState(1)
  const [queueRows, setQueueRows] = useState([])
  const [queuePagination, setQueuePagination] = useState({
    page: 1,
    page_size: PAGE_SIZE,
    total: 0,
    total_pages: 1,
  })
  const [queueLoading, setQueueLoading] = useState(false)
  const [queueError, setQueueError] = useState('')

  const queueRequestId = useRef(0)

  const loadQueue = useCallback(async (page = 1) => {
    const requestId = ++queueRequestId.current

    setQueueLoading(true)
    setQueueError('')

    try {
      const fetchSize = page * PAGE_SIZE

      const [highResult, mediumResult] = await Promise.all([
        apiRequest(
          `/transactions?risk_filter=HIGH&page=1&page_size=${fetchSize}`,
        ),
        apiRequest(
          `/transactions?risk_filter=MEDIUM&page=1&page_size=${fetchSize}`,
        ),
      ])

      if (requestId !== queueRequestId.current) return

      const highRows = getArray(highResult)
      const mediumRows = getArray(mediumResult)

      const highMeta =
        highResult?.pagination && typeof highResult.pagination === 'object'
          ? highResult.pagination
          : highResult

      const mediumMeta =
        mediumResult?.pagination &&
        typeof mediumResult.pagination === 'object'
          ? mediumResult.pagination
          : mediumResult

      const highTotal = Number(highMeta?.total ?? highRows.length)
      const mediumTotal = Number(mediumMeta?.total ?? mediumRows.length)

      const merged = [...highRows, ...mediumRows].sort((a, b) => {
        const ra = getRisk(a) === 'High' ? 0 : 1
        const rb = getRisk(b) === 'High' ? 0 : 1
        if (ra !== rb) return ra - rb

        const aa = toNumber(a.amount) ?? 0
        const ab = toNumber(b.amount) ?? 0
        return ab - aa
      })

      const combinedTotal = highTotal + mediumTotal
      const combinedTotalPages = Math.max(
        1,
        Math.ceil(combinedTotal / PAGE_SIZE),
      )

      const start = (page - 1) * PAGE_SIZE
      const end = start + PAGE_SIZE
      const pageRows = merged.slice(start, end)

      setQueueRows(pageRows)
      setQueuePagination({
        page,
        page_size: PAGE_SIZE,
        total: combinedTotal,
        total_pages: combinedTotalPages,
      })
    } catch (err) {
      if (requestId !== queueRequestId.current) return

      setQueueError(err.message || 'Unable to load the review queue.')
      setQueueRows([])
      setQueuePagination({
        page,
        page_size: PAGE_SIZE,
        total: 0,
        total_pages: 1,
      })
    } finally {
      if (requestId === queueRequestId.current) {
        setQueueLoading(false)
      }
    }
  }, [])

  useEffect(() => {
    const timer = setTimeout(() => {
      loadQueue(queuePage)
    }, 0)

    return () => clearTimeout(timer)
  }, [loadQueue, queuePage, refreshSignal])

  if (loading) {
    return (
      <section className="content-card">
        <div className="panel-padding">
          <Empty
            title="Loading risk data…"
            body="Fetching the current risk distribution."
          />
        </div>
      </section>
    )
  }

  return (
    <>
      <section className="content-card risk-hero">
        <SectionHeading
          eyebrow="RISK POSTURE"
          title="Portfolio risk overview"
          subtitle="How the current ledger splits across HIGH, MEDIUM and LOW risk classifications."
          right={
            <span className="live-label">
              <StatusDot status="online" /> Live
            </span>
          }
        />

        {total === 0 ? (
          <div className="panel-padding">
            <Empty
              title="No risk data yet"
              body="Upload a CSV or refresh to populate the risk distribution."
            />
          </div>
        ) : (
          <>
            <div className="risk-hero-figures">
              <div className="risk-hero-figure">
                <span>Classified records</span>
                <strong>{formatNumber(total)}</strong>
              </div>

              <div className="risk-hero-figure attention">
                <span>Needs attention</span>
                <strong>{formatNumber(needsReview)}</strong>
                <em>{formatPercent(needsReview, total)} of total</em>
              </div>

              <div className="risk-hero-figure clear">
                <span>Low risk</span>
                <strong>{formatNumber(low)}</strong>
                <em>{formatPercent(low, total)} of total</em>
              </div>
            </div>

            <div
              className="risk-meter risk-meter-lg"
              role="img"
              aria-label={`Risk distribution across ${total} records`}
            >
              {segments.map(
                (s) =>
                  s.value > 0 && (
                    <span
                      key={s.key}
                      className={`risk-meter-seg ${s.key}`}
                      style={{ width: `${pct(s.value)}%` }}
                      title={`${s.label}: ${s.value} (${pct(s.value).toFixed(1)}%)`}
                    >
                      <span className="risk-meter-seg-label">{s.label}</span>
                    </span>
                  ),
              )}
            </div>
          </>
        )}
      </section>

      <section className="risk-level-grid" aria-label="Risk level breakdown">
        <RiskLevelCard
          level="high"
          count={high}
          total={total}
          description="Require priority review. Escalate to compliance before settlement."
        />
        <RiskLevelCard
          level="medium"
          count={medium}
          total={total}
          description="Flagged for investigation. Monitor for escalation patterns."
        />
        <RiskLevelCard
          level="low"
          count={low}
          total={total}
          description="Routine activity. No action required under current rules."
        />
      </section>

      <section className="content-card">
        <SectionHeading
          eyebrow="REVIEW QUEUE"
          title="Transactions needing review"
          subtitle="High-risk records first, then medium-risk. Click any row for the full record."
          right={
            <span className="table-count">
              {queueLoading
                ? 'Loading…'
                : `${formatNumber(queuePagination.total)} record${
                    queuePagination.total === 1 ? '' : 's'
                  }`}
            </span>
          }
        />

        <TransactionTable
          transactions={queueRows}
          pagination={queuePagination}
          loading={queueLoading}
          error={queueError}
          emptyMessage="No HIGH or MEDIUM risk transactions are present in the ledger."
          onSelect={onSelect}
          onPageChange={setQueuePage}
        />

        <p className="demo-notice">
          The review queue shows only HIGH and MEDIUM risk transactions,
          fetched directly from /transactions. Pagination matches the
          Transaction ledger (5 rows per page).
        </p>
      </section>
    </>
  )
}

/* ------------------------------------------------------------------
 * Reports
 * ------------------------------------------------------------------ */

function ReportsScreen({ transactions, insights, loading }) {
  const [reports, setReports] = useState([])
  const [reportsLoading, setReportsLoading] = useState(true)
  const [reportsError, setReportsError] = useState('')
  const [refreshVersion, setRefreshVersion] = useState(0)

  useEffect(() => {
    let cancelled = false

    async function loadReports() {
      setReportsLoading(true)
      setReportsError('')

      try {
        const result = await apiRequest('/reports')

        if (cancelled) return

        setReports(Array.isArray(result?.reports) ? result.reports : [])
      } catch (err) {
        if (cancelled) return

        setReports([])
        setReportsError(err.message || 'Unable to retrieve monthly reports.')
      } finally {
        if (!cancelled) {
          setReportsLoading(false)
        }
      }
    }

    loadReports()

    return () => {
      cancelled = true
    }
  }, [refreshVersion])

  const summary = useMemo(() => {
    const loadedRisk = { high: 0, medium: 0, low: 0 }
    const byCountry = new Map()

    transactions.forEach((t) => {
      const risk = getRisk(t)

      if (risk === 'High') loadedRisk.high += 1
      else if (risk === 'Medium') loadedRisk.medium += 1
      else if (risk === 'Low') loadedRisk.low += 1

      const amount = toNumber(t.amount) ?? 0
      const country = t.source_country ?? 'Unknown'

      byCountry.set(country, (byCountry.get(country) ?? 0) + amount)
    })

    const insightTx =
      insights?.transactions && typeof insights.transactions === 'object'
        ? insights.transactions
        : {}

    return {
      totalTransactions: toNumber(insightTx.total) ?? transactions.length,

      byRisk: {
        high: toNumber(insightTx.high) ?? loadedRisk.high,
        medium: toNumber(insightTx.medium) ?? loadedRisk.medium,
        low: toNumber(insightTx.low) ?? loadedRisk.low,
      },

      byCountry: Array.from(byCountry.entries())
        .map(([country, value]) => ({ country, value }))
        .sort((a, b) => b.value - a.value)
        .slice(0, 6),
    }
  }, [transactions, insights])

  const reportingPeriods = new Set(reports.map((report) => report.period)).size

  const csvCount = reports.filter((report) => report.format === 'CSV').length

  const jsonCount = reports.filter((report) => report.format === 'JSON').length

  return (
    <>
      <section className="content-card">
        <SectionHeading
          eyebrow="S3 · MONTHLY REPORT ARCHIVE"
          title="Generated monthly reports"
          subtitle="CSV and JSON reports produced by the monthly report Lambda and stored in the FinTrust reports bucket."
          right={
            <button
              className="secondary-button"
              type="button"
              onClick={() => setRefreshVersion((value) => value + 1)}
              disabled={reportsLoading}
            >
              <RefreshIcon spinning={reportsLoading} />
              {reportsLoading ? 'Refreshing…' : 'Refresh reports'}
            </button>
          }
        />

        {reportsLoading ? (
          <div className="panel-padding">
            <Empty
              title="Loading monthly reports…"
              body="Retrieving report files from the reports API."
            />
          </div>
        ) : reportsError ? (
          <div className="panel-padding" role="alert">
            <Empty
              title="Unable to load monthly reports"
              body={reportsError}
            />

            <button
              className="primary-button"
              type="button"
              onClick={() => setRefreshVersion((value) => value + 1)}
            >
              Try again
            </button>
          </div>
        ) : reports.length === 0 ? (
          <div className="panel-padding">
            <Empty
              title="No monthly reports available"
              body="The reports bucket does not currently contain any monthly CSV or JSON reports."
            />
          </div>
        ) : (
          <>
            <div className="report-summary">
              <div className="report-tile">
                <p>Available files</p>
                <h3>{formatNumber(reports.length)}</h3>
              </div>

              <div className="report-tile">
                <p>Reporting periods</p>
                <h3>{formatNumber(reportingPeriods)}</h3>
              </div>

              <div className="report-tile">
                <p>CSV files</p>
                <h3>{formatNumber(csvCount)}</h3>
              </div>

              <div className="report-tile">
                <p>JSON files</p>
                <h3>{formatNumber(jsonCount)}</h3>
              </div>
            </div>

            <div className="table-wrap">
              <table className="txn-table">
                <thead>
                  <tr>
                    <th scope="col">Reporting period</th>
                    <th scope="col">Report file</th>
                    <th scope="col">Format</th>
                    <th scope="col">Last modified</th>
                    <th scope="col" className="right">
                      File size
                    </th>
                    <th scope="col" className="right">
                      Download
                    </th>
                  </tr>
                </thead>

                <tbody>
                  {reports.map((report) => (
                    <tr key={report.key}>
                      <td>
                        <strong>{formatReportMonth(report.period)}</strong>
                      </td>

                      <td>
                        <span className="mono">{report.filename}</span>
                      </td>

                      <td>
                        <span className="flag-pill">{report.format}</span>
                      </td>

                      <td className="muted">
                        {formatDate(report.last_modified)}
                      </td>

                      <td className="right mono">
                        {formatFileSize(report.size_bytes)}
                      </td>

                      <td className="right">
                        {report.download_url ? (
                          <a
                            className="secondary-button"
                            href={report.download_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            aria-label={`Download ${report.filename}`}
                          >
                            ↓ Download
                          </a>
                        ) : (
                          <span className="muted">Unavailable</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <p className="demo-notice">
              Download links are pre-signed S3 URLs and expire after 15
              minutes. Refresh the reports list to generate fresh links.
            </p>
          </>
        )}
      </section>

      <section className="content-card snapshot-card">
        <SectionHeading
          eyebrow="LIVE TRANSACTION DATA"
          title="Current transaction snapshot"
          subtitle="Full-ledger transaction and risk counts are sourced from /insights. The country breakdown is calculated from the dashboard's currently loaded records."
          right={
            <span className="live-label">
              <StatusDot status="online" />
              Live data
            </span>
          }
        />

        {loading ? (
          <Empty
            title="Loading transaction data…"
            body="Fetching the current dashboard records."
          />
        ) : (
          <>
            <div className="report-summary">
              <div className="report-tile">
                <p>Total transactions</p>
                <h3>{formatNumber(summary.totalTransactions)}</h3>
              </div>

              <div className="report-tile high">
                <p>High risk</p>
                <h3>{formatNumber(summary.byRisk.high)}</h3>
              </div>

              <div className="report-tile medium">
                <p>Medium risk</p>
                <h3>{formatNumber(summary.byRisk.medium)}</h3>
              </div>

              <div className="report-tile low">
                <p>Low risk</p>
                <h3>{formatNumber(summary.byRisk.low)}</h3>
              </div>
            </div>

            <SectionHeading
              eyebrow="SOURCE COUNTRY"
              title="Transaction value by origin"
              subtitle="Transaction amounts grouped by source country in the currently loaded dashboard records."
            />

            {summary.byCountry.length === 0 ? (
              <Empty
                title="No transaction data"
                body="There are no loaded records to summarise."
              />
            ) : (
              <ul className="hbars">
                {summary.byCountry.map((row) => {
                  const max = summary.byCountry[0].value

                  return (
                    <li key={row.country}>
                      <span className="hlabel mono">{row.country}</span>

                      <span className="htrack">
                        <span
                          className="hfill green"
                          style={{
                            width: `${
                              max > 0 ? (row.value / max) * 100 : 0
                            }%`,
                          }}
                        />
                      </span>

                      <span className="hcount mono">
                        {formatCompactCurrency(row.value)}
                      </span>
                    </li>
                  )
                })}
              </ul>
            )}
          </>
        )}

        <p className="demo-notice">
          Transaction and risk counts come from the /insights endpoint. The
          country breakdown uses the dashboard's currently loaded records, so
          it is not a full-ledger monetary aggregate. The complete monthly
          report is generated separately by report.py.
        </p>
      </section>
    </>
  )
}

/* ------------------------------------------------------------------
 * App
 * ------------------------------------------------------------------ */

function App() {
  const [activePage, setActivePage] = useState('overview')

  const [transactions, setTransactions] = useState([])
  const [insights, setInsights] = useState(null)

  const [ledgerTransactions, setLedgerTransactions] = useState([])
  const [ledgerPagination, setLedgerPagination] = useState({
    page: 1,
    page_size: PAGE_SIZE,
    total: 0,
    total_pages: 1,
  })
  const [ledgerLoading, setLedgerLoading] = useState(false)
  const [ledgerError, setLedgerError] = useState('')

  const [apiStatus, setApiStatus] = useState('checking')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [uploadMessage, setUploadMessage] = useState('')
  const [uploading, setUploading] = useState(false)
  const [selectedTransaction, setSelectedTransaction] = useState(null)

  const [processingJob, setProcessingJob] = useState(null)

  const [toast, setToast] = useState(null)

  const toastTimerRef = useRef(null)
  const toastQueueRef = useRef([])

  const displayToast = useCallback((notification) => {
    if (toastTimerRef.current) {
      clearTimeout(toastTimerRef.current)
    }

    setToast(notification)

    toastTimerRef.current = setTimeout(() => {
      toastTimerRef.current = null

      const next = toastQueueRef.current.shift()

      if (next) {
        displayToastRef.current(next)
      } else {
        setToast(null)
      }
    }, 4500)
  }, [])

  const displayToastRef = useRef(displayToast)

  useEffect(() => {
    displayToastRef.current = displayToast
  }, [displayToast])

  const notify = useCallback((title, message, type = 'success') => {
    toastQueueRef.current = []

    if (toastTimerRef.current) {
      clearTimeout(toastTimerRef.current)
      toastTimerRef.current = null
    }

    displayToastRef.current({ title, message, type })
  }, [])

  const dismissToast = useCallback(() => {
    if (toastTimerRef.current) {
      clearTimeout(toastTimerRef.current)
      toastTimerRef.current = null
    }

    const next = toastQueueRef.current.shift()

    if (next) {
      displayToastRef.current(next)
    } else {
      setToast(null)
    }
  }, [])

  useEffect(() => {
    return () => {
      if (toastTimerRef.current) {
        clearTimeout(toastTimerRef.current)
      }
    }
  }, [])

  const ledgerRequestId = useRef(0)

  const [theme, setTheme] = useState('new')

  const toggleTheme = useCallback(() => {
    setTheme((current) => (current === 'new' ? 'classic' : 'new'))
  }, [])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document.body.dataset.theme = theme

    return () => {
      delete document.documentElement.dataset.theme
      delete document.body.dataset.theme
    }
  }, [theme])

  const fetchLedger = useCallback(
    async ({
      page = 1,
      search = '',
      riskFilter = 'All',
      flagFilter = 'All',
    } = {}) => {
      const requestId = ++ledgerRequestId.current

      setLedgerLoading(true)
      setLedgerError('')

      try {
        const params = new URLSearchParams({
          page: String(page),
          page_size: String(PAGE_SIZE),
        })

        if (search.trim()) {
          params.set('search', search.trim())
        }

        if (riskFilter !== 'All') {
          params.set('risk_filter', riskFilter.toUpperCase())
        }

        if (flagFilter !== 'All') {
          params.set('flag_filter', flagFilter)
        }

        const result = await apiRequest(`/transactions?${params.toString()}`)

        if (requestId !== ledgerRequestId.current) return

        const rows = getArray(result)
        const metadata =
          result?.pagination && typeof result.pagination === 'object'
            ? result.pagination
            : result

        const returnedPage = Number(metadata?.page ?? page)
        const returnedPageSize = Number(metadata?.page_size ?? PAGE_SIZE)
        const returnedTotal = Number(
          metadata?.total ?? metadata?.total_count ?? rows.length,
        )

        const returnedTotalPages = Number(
          metadata?.total_pages ??
            Math.max(1, Math.ceil(returnedTotal / returnedPageSize)),
        )

        setLedgerTransactions(rows)
        setLedgerPagination({
          page: returnedPage,
          page_size: returnedPageSize,
          total: returnedTotal,
          total_pages: returnedTotalPages,
        })
      } catch (err) {
        if (requestId !== ledgerRequestId.current) return

        setLedgerError(err.message || 'Unable to load transactions.')
        setLedgerTransactions([])
        setLedgerPagination({
          page,
          page_size: PAGE_SIZE,
          total: 0,
          total_pages: 1,
        })
      } finally {
        if (requestId === ledgerRequestId.current) {
          setLedgerLoading(false)
        }
      }
    },
    [],
  )

  const loadDashboard = useCallback(async () => {
    setLoading(true)
    setError('')

    try {
      await apiRequest('/health')
      setApiStatus('online')

      const [txResult, insightResult] = await Promise.all([
        apiRequest('/transactions?page=1&page_size=20'),
        apiRequest('/insights'),
      ])

      setTransactions(getArray(txResult))
      setInsights(insightResult)
    } catch (err) {
      setApiStatus('offline')

      setError(
        `${err.message}. Check the FinTrust API proxy and backend availability.`
      )

      setTransactions([])
      setInsights(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadDashboard()
  }, [loadDashboard])

  useEffect(() => {
    if (!processingJob?.uploadId) return

    const uploadId = processingJob.uploadId
    let cancelled = false
    let timer
    let previousStages = {}
    let completionNotified = false

    async function pollProgress() {
      try {
        const result = await apiRequest(
          `/uploads/${encodeURIComponent(uploadId)}/progress`,
        )

        if (cancelled) return

        const progress =
          result?.progress && typeof result.progress === 'object'
            ? result.progress
            : result

        const status = String(progress?.status ?? '').toUpperCase()
        const currentStages = progress?.stages ?? {}

        const newlyCompleted = PROCESSING_STAGES.filter((stage) => {
          const current = String(
            currentStages[stage.apiKey] ?? '',
          ).toUpperCase()

          const previous = String(
            previousStages[stage.apiKey] ?? '',
          ).toUpperCase()

          return current === 'COMPLETED' && previous !== 'COMPLETED'
        })

        previousStages = { ...currentStages }

        setProcessingJob((job) =>
          !job || job.uploadId !== uploadId
            ? job
            : {
                ...job,
                progress,
                progressError: '',
              },
        )

        if (status === 'FAILED') {
          notify(
            'Processing failed',
            progress?.failure_reason ||
              'The CSV processing workflow failed.',
            'error',
          )
          return
        }

        if (status === 'COMPLETED') {
          if (!completionNotified) {
            completionNotified = true

            const duplicateCount = Number(progress?.duplicate_records ?? 0)

            notify(
              'Processing completed',
              'All six processing stages have completed successfully.',
              'success',
            )

            if (Number.isFinite(duplicateCount) && duplicateCount > 0) {
              toastQueueRef.current.push({
                title: 'Duplicate transactions detected',
                message: `${formatNumber(duplicateCount)} transactions were already processed. Existing records were reused, preventing duplicate entries and unnecessary risk calculations.`,
                type: 'success',
              })
            }
          }

          return
        }

        if (newlyCompleted.length > 0) {
          const latestStage = newlyCompleted[newlyCompleted.length - 1]

          notify(
            `${latestStage.title} completed`,
            latestStage.description,
            'success',
          )
        }
      } catch (err) {
        if (cancelled) return

        setProcessingJob((job) =>
          !job || job.uploadId !== uploadId
            ? job
            : {
                ...job,
                progressError:
                  err.message || 'Progress request failed.',
              },
        )
      }

      if (!cancelled) {
        timer = setTimeout(pollProgress, 1000)
      }
    }

    pollProgress()

    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [processingJob?.uploadId, notify])

  async function processFile(file) {
    if (!file) return

    if (!file.name.toLowerCase().endsWith('.csv')) {
      setUploadMessage('Please select a CSV file.')
      return
    }

    if (file.size === 0) {
      setUploadMessage('The selected CSV file is empty.')
      return
    }

    setUploading(true)
    setUploadMessage(`Uploading "${file.name}"…`)

    try {
      const csvContent = await file.text()

      const result = await apiRequest('/upload', {
        method: 'POST',
        headers: { 'Content-Type': 'text/csv' },
        body: csvContent,
      })

      const serverMessage =
        result && typeof result === 'object' && result.message
          ? result.message
          : 'The CSV was accepted for processing.'

      const uploadId = result?.upload_id || result?.id

      if (!uploadId) {
        throw new Error(
          'The API accepted the upload but did not return an upload ID.',
        )
      }

      setUploadMessage(`${file.name}: ${serverMessage}`)

      setProcessingJob({
        uploadId,
        fileName: file.name,
        progress: null,
        progressError: '',
      })

      notify(
        'Upload accepted',
        'Your CSV file was received. Processing has started.',
      )
    } catch (err) {
      setUploadMessage(`Upload failed for "${file.name}": ${err.message}`)

      notify(
        'Upload failed',
        err.message || 'Unable to upload the CSV file.',
        'error',
      )
    } finally {
      setUploading(false)
    }
  }

  const clearProcessingJob = useCallback(() => {
    setProcessingJob(null)
    setUploadMessage('')
  }, [])

  const subtitles = {
    overview:
      'Live transaction activity, risk classification and pipeline health across the FinTrust environment.',
    transactions:
      'Upload new records and review every transaction returned by the API.',
    risk: 'Risk posture, level breakdown and a prioritised review queue drawn from the live ledger.',
    reports:
      'Access generated monthly CSV and JSON reports stored in the FinTrust S3 reports bucket, alongside live transaction insights.',
  }

  const [refreshSignal, setRefreshSignal] = useState(0)

  return (
    <div className="app-shell" data-theme={theme}>
      <Sidebar
        activePage={activePage}
        onNavigate={setActivePage}
        apiStatus={apiStatus}
      />

      <main className="main-content" id="overview">
        <Topbar
          activePage={activePage}
          apiStatus={apiStatus}
          onRefresh={() => {
            loadDashboard()
            setRefreshSignal((n) => n + 1)
          }}
          loading={loading}
          theme={theme}
          onToggleTheme={toggleTheme}
        />

        <div className={`dashboard-content page-${activePage}`}>
          <section className="page-heading">
            <div>
              <p className="eyebrow">TRANSACTION INTELLIGENCE</p>

              <h1>
                {navigation.find((n) => n.key === activePage)?.label ??
                  'Overview'}
              </h1>

              <p className="subtitle">{subtitles[activePage]}</p>
            </div>
          </section>

          {error && (
            <section className="content-card" role="alert">
              <SectionHeading
                eyebrow="CONNECTION ERROR"
                title="Unable to load live data"
                subtitle={error}
                right={<StatusDot status="offline" />}
              />

              <div className="panel-padding">
                <button
                  className="primary-button"
                  type="button"
                  onClick={loadDashboard}
                  disabled={loading}
                >
                  {loading ? 'Connecting…' : 'Try again'}
                </button>
              </div>
            </section>
          )}

          {activePage === 'overview' && (
            <OverviewScreen
              transactions={transactions}
              insights={insights}
              loading={loading}
            />
          )}

          {activePage === 'transactions' && (
            <TransactionsScreen
              transactions={ledgerTransactions}
              pagination={ledgerPagination}
              loading={ledgerLoading}
              ledgerError={ledgerError}
              onFetch={fetchLedger}
              onSelect={setSelectedTransaction}
              onFile={processFile}
              uploading={uploading}
              uploadMessage={uploadMessage}
              processingJob={processingJob}
              onUploadAnother={clearProcessingJob}
            />
          )}

          {activePage === 'risk' && (
            <RiskOverviewScreen
              transactions={transactions}
              insights={insights}
              loading={loading}
              onSelect={setSelectedTransaction}
              refreshSignal={refreshSignal}
            />
          )}

          {activePage === 'reports' && (
            <ReportsScreen
              transactions={transactions}
              insights={insights}
              loading={loading}
            />
          )}

          <footer className="page-footer">
            <span>FinTrust Bank SA</span>
            <span className="footer-separator">·</span>
            <span>Transaction Insights &amp; Risk Monitoring</span>
            <span className="footer-separator">·</span>
            <span>Cloud to Solutions Accelerator · Praesignis</span>
          </footer>
        </div>
      </main>

      <DetailDrawer
        transaction={selectedTransaction}
        onClose={() => setSelectedTransaction(null)}
      />

      <ToastNotification toast={toast} onDismiss={dismissToast} />

      <BackToTop />
    </div>
  )
}

export default App