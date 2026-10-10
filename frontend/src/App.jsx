
import { useCallback, useEffect, useRef, useState } from 'react'
import './App.css'

const API_BASE =
  'https://a1tia7lthb.execute-api.eu-north-1.amazonaws.com/prod'
const API_KEY = import.meta.env.VITE_API_KEY

const navigation = [
  { label: 'Overview', icon: '▦', href: '#overview' },
  { label: 'Transactions', icon: '↔', href: '#transactions' },
  { label: 'Risk monitoring', icon: '◈', href: '#risk' },
  { label: 'Investigations', icon: '◎', href: '#investigations' },
]

async function apiRequest(path, options = {}) {
  if (!API_KEY) {
    throw new Error(
      'API key is missing. Configure VITE_API_KEY in frontend/.env.local.',
    )
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'x-api-key': API_KEY,
      ...(options.body
        ? { 'Content-Type': 'application/json' }
        : {}),
      ...options.headers,
    },
  })

  const text = await response.text()
  let data = null

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

function getArray(data) {
  if (Array.isArray(data)) return data
  if (!data || typeof data !== 'object') return []

  for (const key of ['transactions', 'items', 'records', 'results', 'data']) {
    if (Array.isArray(data[key])) return data[key]
  }

  return []
}

function getValue(object, keys) {
  for (const key of keys) {
    if (object?.[key] !== undefined && object[key] !== null) {
      return object[key]
    }
  }

  return null
}

function toNumber(value) {
  if (value === null || value === undefined || value === '') return null

  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

function formatNumber(value) {
  const number = toNumber(value)
  return number === null ? '—' : number.toLocaleString('en-ZA')
}

function formatCurrency(value, currency = 'ZAR') {
  const number = toNumber(value)
  if (number === null) return '—'

  try {
    return number.toLocaleString('en-ZA', {
      style: 'currency',
      currency: currency || 'ZAR',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })
  } catch {
    return `${currency || 'ZAR'} ${number.toFixed(2)}`
  }
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
    second: '2-digit',
    hour12: false,
  })
}

function getTransactionId(transaction, index = 0) {
  return transaction?.transaction_id ?? `Record ${index + 1}`
}

function getRisk(transaction) {
  const rawRisk = String(transaction?.risk_flag ?? '').toUpperCase()

  if (rawRisk === 'HIGH') return 'High'
  if (rawRisk === 'MEDIUM') return 'Medium'
  if (rawRisk === 'LOW') return 'Low'

  return 'Unclassified'
}

function getRiskFlags(transaction) {
  const risk = transaction?.risk_flag

  if (!risk) return 'Not classified'
  return risk
}

function StatusDot({ status = 'default' }) {
  return <span className={`status-dot ${status}`} aria-hidden="true" />
}

function SectionHeading({ title, subtitle, right }) {
  return (
    <div className="section-heading">
      <div>
        <h2>{title}</h2>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {right}
    </div>
  )
}

function Sidebar({ activePage, onNavigate, apiStatus }) {
  return (
    <aside className="sidebar">
      <a
        className="brand"
        href="#overview"
        aria-label="FinTrust home"
        onClick={() => onNavigate('Overview')}
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
            <a
              className={`nav-item ${
                activePage === item.label ? 'active' : ''
              }`}
              href={item.href}
              key={item.label}
              onClick={() => onNavigate(item.label)}
            >
              <span className="nav-icon" aria-hidden="true">
                {item.icon}
              </span>
              <span>{item.label}</span>
            </a>
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

function Topbar({ onUpload, activePage, apiStatus }) {
  return (
    <header className="topbar">
      <div className="breadcrumb">
        FinTrust <span>/</span> <strong>{activePage}</strong>
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
          className="primary-button"
          type="button"
          onClick={onUpload}
        >
          Upload CSV <span aria-hidden="true">↥</span>
        </button>
      </div>
    </header>
  )
}

function PageHeading({ activePage, onUpload, onRefresh, loading }) {
  const descriptions = {
    Overview:
      'Monitor transaction activity and review risk insights across the FinTrust environment.',
    Transactions:
      'Review transaction records using the actual FinTrust database fields.',
    'Risk monitoring':
      'Monitor available risk classifications and rule-based insights.',
    Investigations:
      'Review transaction records and their available risk classifications.',
  }

  return (
    <section className="page-heading">
      <div>
        <p className="eyebrow">TRANSACTION INTELLIGENCE</p>
        <h1>{activePage === 'Overview' ? 'Risk overview' : activePage}</h1>
        <p className="subtitle">
          {descriptions[activePage] ?? descriptions.Overview}
        </p>
      </div>

      <div className="page-heading-actions">
        <button
          className="secondary-button"
          type="button"
          onClick={onRefresh}
          disabled={loading}
        >
          <span aria-hidden="true">↻</span> Refresh
        </button>

        <button
          className="primary-button"
          type="button"
          onClick={onUpload}
        >
          Upload CSV <span aria-hidden="true">↥</span>
        </button>
      </div>
    </section>
  )
}

function SummaryCards({ transactions, insights }) {
  const insightTransactions =
    insights?.transactions &&
    typeof insights.transactions === 'object'
      ? insights.transactions
      : {}

  const riskCounts = transactions.reduce(
    (counts, transaction) => {
      const risk = getRisk(transaction)
      if (risk === 'High') counts.high += 1
      if (risk === 'Medium') counts.medium += 1
      if (risk === 'Low') counts.low += 1
      return counts
    },
    { high: 0, medium: 0, low: 0 },
  )

  const hasAmounts = transactions.some(
    (transaction) => toNumber(transaction.amount) !== null,
  )

  const returnedValue = transactions.reduce(
    (total, transaction) =>
      total + (toNumber(transaction.amount) ?? 0),
    0,
  )

  const cards = [
    {
      label: 'Total transactions',
      value: formatNumber(
        insightTransactions.total ?? transactions.length,
      ),
      note: 'Total records in the database',
      icon: '↔',
      color: 'blue',
    },
    {
      label: 'High-risk transactions',
      value: formatNumber(insightTransactions.high ?? riskCounts.high),
      note: 'Transactions with HIGH risk flag',
      icon: '!',
      color: 'red',
    },
    {
      label: 'Medium-risk transactions',
      value: formatNumber(
        insightTransactions.medium ?? riskCounts.medium,
      ),
      note: 'Transactions with MEDIUM risk flag',
      icon: '◎',
      color: 'amber',
    },
    {
      label: 'Returned transaction value',
      value: hasAmounts ? formatCurrency(returnedValue) : '—',
      note: 'Sum of transactions on this page',
      icon: 'R',
      color: 'green',
    },
  ]

  return (
    <section className="summary-grid" aria-label="Transaction summary">
      {cards.map((card) => (
        <article className="summary-card" key={card.label}>
          <div className="summary-card-top">
            <p>{card.label}</p>
            <span
              className={`summary-icon ${card.color}`}
              aria-hidden="true"
            >
              {card.icon}
            </span>
          </div>
          <h2>{card.value}</h2>
          <p className="summary-note">{card.note}</p>
        </article>
      ))}
    </section>
  )
}

function RiskMonitoring({ insights, transactions }) {
  const insightTransactions =
    insights?.transactions &&
    typeof insights.transactions === 'object'
      ? insights.transactions
      : {}

  const counts = transactions.reduce(
    (result, transaction) => {
      const risk = getRisk(transaction)
      if (risk === 'High') result.high += 1
      if (risk === 'Medium') result.medium += 1
      if (risk === 'Low') result.low += 1
      return result
    },
    { high: 0, medium: 0, low: 0 },
  )

  const levels = [
    {
      level: 'high',
      title: 'High risk',
      count: insightTransactions.high ?? counts.high,
      description: 'Transactions with a HIGH risk flag.',
      symbol: '!',
    },
    {
      level: 'medium',
      title: 'Medium risk',
      count: insightTransactions.medium ?? counts.medium,
      description: 'Transactions with a MEDIUM risk flag.',
      symbol: '◈',
    },
    {
      level: 'low',
      title: 'Low risk',
      count: insightTransactions.low ?? counts.low,
      description: 'Transactions with a LOW risk flag.',
      symbol: '✓',
    },
  ]

  return (
    <section className="content-card" id="risk">
      <SectionHeading
        title="Risk monitoring"
        subtitle="Available classifications from the transactions risk_flag field."
        right={
          <span className="live-label">
            <StatusDot status="online" />
            GET /insights
          </span>
        }
      />

      <div className="risk-levels">
        {levels.map((risk) => (
          <article
            className={`risk-level ${risk.level}`}
            key={risk.level}
          >
            <span className="risk-symbol" aria-hidden="true">
              {risk.symbol}
            </span>
            <div>
              <strong>
                {risk.title} · {formatNumber(risk.count)}
              </strong>
              <p>{risk.description}</p>
            </div>
          </article>
        ))}
      </div>

      <p className="demo-notice">
        Risk counts come from the API insights response or the transactions
        returned to this dashboard. A NULL risk_flag is shown as unclassified,
        not automatically assigned a risk level.
      </p>
    </section>
  )
}

function TransactionsTable({ transactions, loading }) {
  return (
    <section className="content-card" id="transactions">
      <SectionHeading
        title="Recent transactions"
        subtitle="Records returned from PostgreSQL using the transactions table schema."
        right={
          <span className="table-count">
            {loading ? 'Loading…' : `${transactions.length} records`}
          </span>
        }
      />

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Transaction ID</th>
              <th scope="col">Account ID</th>
              <th scope="col">Transaction date</th>
              <th scope="col">Amount</th>
              <th scope="col">Currency</th>
              <th scope="col">Type</th>
              <th scope="col">Source country</th>
              <th scope="col">Destination country</th>
              <th scope="col">Risk flag</th>
              <th scope="col">Created at</th>
            </tr>
          </thead>

          <tbody>
            {transactions.map((transaction, index) => {
              const risk = getRisk(transaction)
              const transactionId = getTransactionId(transaction, index)

              return (
                <tr key={String(transactionId)}>
                  <td>
                    <strong>{transactionId}</strong>
                  </td>
                  <td>{transaction.account_id ?? '—'}</td>
                  <td>{formatDate(transaction.tx_date)}</td>
                  <td className="amount">
                    {formatCurrency(
                      transaction.amount,
                      transaction.currency,
                    )}
                  </td>
                  <td>{transaction.currency ?? '—'}</td>
                  <td>{transaction.transaction_type ?? '—'}</td>
                  <td>{transaction.source_country ?? '—'}</td>
                  <td>{transaction.destination_country ?? '—'}</td>
                  <td>
                    <span className={`risk-badge ${risk.toLowerCase()}`}>
                      <span className="badge-dot" />
                      {getRiskFlags(transaction)}
                    </span>
                  </td>
                  <td>{formatDate(transaction.created_at)}</td>
                </tr>
              )
            })}

            {!loading && transactions.length === 0 && (
              <tr>
                <td colSpan={10}>
                  No transactions were returned. Refresh the dashboard or
                  check the API response and database records.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <p className="demo-notice">
        The table displays the ten fields returned by the existing
        transactions query. NULL risk flags remain unclassified. No sample
        ledger records are inserted into the dashboard.
      </p>
    </section>
  )
}

function QuickActions({ onUpload, onRefresh, loading }) {
  return (
    <section className="quick-actions" id="investigations">
      <div>
        <div className="quick-action-icon" aria-hidden="true">
          ↥
        </div>
        <div>
          <h3>Upload transaction CSV</h3>
          <p>Select a transaction CSV file to prepare it for ingestion.</p>
        </div>
        <button
          className="primary-button"
          type="button"
          onClick={onUpload}
          style={{ marginLeft: 'auto', minHeight: 36, padding: '0 12px' }}
        >
          Choose file
        </button>
      </div>

      <div>
        <div className="quick-action-icon" aria-hidden="true">
          ↻
        </div>
        <div>
          <h3>Refresh transaction data</h3>
          <p>Request the latest available transactions and risk summaries.</p>
        </div>
        <button
          className="secondary-button"
          type="button"
          onClick={onRefresh}
          disabled={loading}
          style={{ marginLeft: 'auto', minHeight: 36, padding: '0 12px' }}
        >
          {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>
    </section>
  )
}

function App() {
  const fileInputRef = useRef(null)

  const [activePage, setActivePage] = useState('Overview')
  const [transactions, setTransactions] = useState([])
  const [insights, setInsights] = useState(null)
  const [apiStatus, setApiStatus] = useState('checking')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [uploadMessage, setUploadMessage] = useState('')
  const [uploading, setUploading] = useState(false)

  const loadDashboard = useCallback(async () => {
    setLoading(true)
    setError('')

    try {
      await apiRequest('/health')
      setApiStatus('online')

      const [transactionResult, insightResult] = await Promise.all([
        apiRequest('/transactions'),
        apiRequest('/insights'),
      ])

      setTransactions(getArray(transactionResult))
      setInsights(insightResult)
    } catch (err) {
      setApiStatus('offline')
      setError(
        `${err.message}. Check the API key, API availability and CORS configuration for localhost:5173.`,
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

  function openFilePicker() {
    if (uploading) return
    setUploadMessage('')
    fileInputRef.current?.click()
  }

  async function handleFileSelected(event) {
    const file = event.target.files?.[0]
    event.target.value = ''

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
    setUploadMessage(`Uploading "${file.name}"...`)

    try {
      const csvContent = await file.text()

      const result = await apiRequest('/upload', {
        method: 'POST',
        headers: {
          'Content-Type': 'text/csv',
        },
        body: csvContent,
      })

      const serverMessage =
        result && typeof result === 'object' && result.message
          ? result.message
          : 'The CSV was accepted for processing.'

      setUploadMessage(
        `${file.name}: ${serverMessage} Processing is asynchronous. Refresh after ingestion has completed to load the latest records.`,
      )
    } catch (err) {
      setUploadMessage(`Upload failed for "${file.name}": ${err.message}`)
    } finally {
      setUploading(false)
    }
  }

  function handleNavigation(label) {
    setActivePage(label)
  }

  return (
    <div className="app-shell">
      <input
        ref={fileInputRef}
        type="file"
        accept=".csv,text/csv"
        onChange={handleFileSelected}
        hidden
        aria-label="Choose transaction CSV file"
        disabled={uploading}
      />

      <Sidebar
        activePage={activePage}
        onNavigate={handleNavigation}
        apiStatus={apiStatus}
      />

      <main className="main-content" id="overview">
        <Topbar
          onUpload={openFilePicker}
          activePage={activePage}
          apiStatus={apiStatus}
        />

        <div className="dashboard-content">
          <PageHeading
            activePage={activePage}
            onUpload={openFilePicker}
            onRefresh={loadDashboard}
            loading={loading}
          />

          {error && (
            <section className="content-card" role="alert">
              <SectionHeading
                title="Unable to load live data"
                subtitle={error}
                right={<StatusDot status="offline" />}
              />
              <button
                className="primary-button"
                type="button"
                onClick={loadDashboard}
                disabled={loading}
              >
                {loading ? 'Connecting…' : 'Try again'}
              </button>
            </section>
          )}

          {(uploadMessage || uploading) && (
            <div className="content-card" role="status" aria-live="polite">
              <p>{uploadMessage}</p>
              {uploading && (
                <p>Please keep this page open while the upload is sent.</p>
              )}
            </div>
          )}

          {loading && !error && (
            <p className="loading-message" role="status">
              Connecting to FinTrust and retrieving dashboard data…
            </p>
          )}

          <SummaryCards transactions={transactions} insights={insights} />
          <RiskMonitoring insights={insights} transactions={transactions} />
          <TransactionsTable
            transactions={transactions}
            loading={loading}
          />

          <QuickActions
            onUpload={openFilePicker}
            onRefresh={loadDashboard}
            loading={loading}
          />

          <footer className="page-footer">
            <span>FinTrust Bank SA</span>
            <span className="footer-separator">·</span>
            <span>Transaction Insights &amp; Risk Monitoring</span>
            <span className="footer-separator">·</span>
            <span>Demo build v0.2</span>
          </footer>
        </div>
      </main>
    </div>
  )
}

export default App