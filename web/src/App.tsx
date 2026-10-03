import { useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  Activity,
  ArrowUpRight,
  Check,
  CircleAlert,
  CircleCheck,
  Clock3,
  FileClock,
  LayoutDashboard,
  LoaderCircle,
  Network,
  PanelLeft,
  Search,
  ShieldCheck,
  X,
} from 'lucide-react'
import './App.css'

type ApprovalStatus = 'pending' | 'approved' | 'rejected'
type Severity = 'high' | 'medium' | 'low' | 'critical'

type Approval = {
  approval_id: string
  status: ApprovalStatus
  plan: {
    summary: string
    commands: { command: string; scope: string }[]
    model_metadata: { provider: string; model: string }
  }
  finding: {
    rule_id: string
    device_id: string
    severity: Severity
    expected: string
    evidence: string[]
  }
}

type Scenario = {
  scenario_id: string
  workflow: {
    status: string
    findings: unknown[]
    approvals: Approval[]
  }
  live: {
    execution: { success: boolean; postcheck_hash: string }
    reaudit: {
      remediation_succeeded: boolean
      post_compliant: boolean
      unresolved_findings: unknown[]
      regression_findings: unknown[]
    }
  } | null
}

const API_BASE = '/api'
const scenarioId = 'frontend-demo-001'
const deviceId = 'lab-router-01'
const initialConfiguration = 'ntp server 10.10.10.20\n'
const rules = [{
  rule_id: 'ntp-approved-server',
  version: '1.0.0',
  description: 'NTP server must be approved',
  platform: 'cisco_ios',
  expected_state: 'ntp server 10.10.10.10',
  allowed_scope: ['ntp'],
  ground_truth_commands: ['ntp server 10.10.10.10'],
  severity: 'medium',
}]

const navItems: { label: string; icon: LucideIcon }[] = [
  { label: 'Overview', icon: LayoutDashboard },
  { label: 'Approvals', icon: CircleCheck },
  { label: 'Devices', icon: Network },
  { label: 'Audit logs', icon: FileClock },
  { label: 'Experiments', icon: Activity },
]

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail ?? `Request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}

function App() {
  const [scenario, setScenario] = useState<Scenario | null>(null)
  const [selectedId, setSelectedId] = useState('')
  const [activeView, setActiveView] = useState('Approvals')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const approvals = scenario?.workflow.approvals ?? []
  const selected = approvals.find((approval) => approval.approval_id === selectedId) ?? approvals[0]
  const pendingCount = approvals.filter((approval) => approval.status === 'pending').length
  const approvedCount = approvals.filter((approval) => approval.status === 'approved').length
  const readyToExecute = approvals.length > 0 && pendingCount === 0 && !scenario?.live

  const showNotice = (message: string) => {
    setNotice(message)
    window.setTimeout(() => setNotice(''), 2800)
  }

  const runAudit = async () => {
    setBusy(true)
    setError('')
    try {
      const next = await request<Scenario>('/scenarios/audit', {
        method: 'POST',
        body: JSON.stringify({
          scenario_id: scenarioId,
          configuration: initialConfiguration,
          device_id: deviceId,
          host: '192.0.2.10',
          device_type: 'cisco_ios',
          rules,
          requested_by: 'operator-01',
        }),
      })
      setScenario(next)
      setSelectedId(next.workflow.approvals[0]?.approval_id ?? '')
      showNotice(`Audit complete: ${next.workflow.approvals.length} approval(s) created.`)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Audit failed')
    } finally {
      setBusy(false)
    }
  }

  const decide = async (status: 'approve' | 'reject') => {
    if (!selected || selected.status !== 'pending') return
    setBusy(true)
    setError('')
    try {
      const updated = await request<Approval>(
        `/approvals/${selected.approval_id}/${status}`,
        { method: 'POST', body: JSON.stringify({ decided_by: 'operator-01' }) },
      )
      setScenario((current) => current && {
        ...current,
        workflow: {
          ...current.workflow,
          approvals: current.workflow.approvals.map((approval) =>
            approval.approval_id === updated.approval_id ? updated : approval,
          ),
        },
      })
      showNotice(`${updated.approval_id} marked ${updated.status}.`)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Decision failed')
    } finally {
      setBusy(false)
    }
  }

  const execute = async () => {
    if (!scenario) return
    setBusy(true)
    setError('')
    try {
      const updated = await request<Scenario>(`/scenarios/${scenario.scenario_id}/execute`, {
        method: 'POST',
      })
      setScenario(updated)
      showNotice('Scenario executed and re-audited.')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Execution failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><div className="brand-mark"><ShieldCheck size={18} /></div><div><strong>Sentinel</strong><span>Network control plane</span></div></div>
        <div className="workspace-switcher"><div className="workspace-dot" /><div><span>Workspace</span><strong>Virtual Lab</strong></div></div>
        <nav className="nav-list" aria-label="Primary navigation">
          {navItems.map(({ label, icon: Icon }) => <button className={`nav-item ${activeView === label ? 'active' : ''}`} key={label} onClick={() => setActiveView(label)} type="button"><Icon size={17} /><span>{label}</span>{label === 'Approvals' && <b>{pendingCount}</b>}</button>)}
        </nav>
        <div className="sidebar-bottom"><div className="system-status"><span className="status-pulse" />API control plane</div><div className="user-row"><div className="avatar">AK</div><div><strong>Alex Kim</strong><span>Operator</span></div><PanelLeft size={16} /></div></div>
      </aside>
      <main className="main-content">
        <header className="topbar"><div className="mobile-brand"><div className="brand-mark"><ShieldCheck size={18} /></div><strong>Sentinel</strong></div><div className="breadcrumbs"><span>Workspace</span><span>/</span><strong>{activeView}</strong></div><div className="top-actions"><button className="icon-button" title="Search" aria-label="Search" type="button"><Search size={18} /></button><div className="top-avatar">AK</div></div></header>
        <div className="content-wrap">
          <section className="page-heading"><div><p className="eyebrow">CONTROL CENTER <span>•</span> OCT 03, 2026</p><h1>{activeView}</h1><p className="subheading">Review proposed network changes before they reach your lab.</p></div><button className="approve-button audit-button" disabled={busy} onClick={runAudit} type="button">{busy ? <LoaderCircle className="spin" size={16} /> : <Activity size={16} />}Run audit</button></section>
          {error && <div className="error-banner"><CircleAlert size={17} />{error}</div>}
          <section className="stat-grid" aria-label="Scenario summary">
            <div className="stat-card"><div className="stat-icon orange"><Clock3 size={17} /></div><span>Awaiting approval</span><strong>{pendingCount}</strong><small>Scenario plans pending</small></div>
            <div className="stat-card"><div className="stat-icon green"><CircleCheck size={17} /></div><span>Approved plans</span><strong>{approvedCount}</strong><small>{scenario ? `${approvals.length} total plans` : 'Run an audit to begin'}</small></div>
            <div className="stat-card"><div className="stat-icon blue"><Network size={17} /></div><span>Scenario device</span><strong>{scenario ? deviceId : '—'}</strong><small>Virtual lab target</small></div>
            <div className="stat-card"><div className="stat-icon slate"><Activity size={17} /></div><span>Re-audit</span><strong>{scenario?.live ? (scenario.live.reaudit.post_compliant ? 'PASS' : 'FAIL') : '—'}</strong><small>{scenario?.live ? 'Post-check completed' : 'Not executed'}</small></div>
          </section>
          <section className="dashboard-grid">
            <div className="panel queue-panel">
              <div className="panel-heading"><div><span className="section-kicker">SCENARIO REVIEW QUEUE</span><h2>{scenario ? scenario.scenario_id : 'No scenario loaded'} <span className="count-pill">{approvals.length}</span></h2></div><button className="filter-button" disabled={!readyToExecute || busy} onClick={execute} type="button">{readyToExecute ? 'Execute scenario' : 'All plans'} <ArrowUpRight size={14} /></button></div>
              <div className="approval-list">{approvals.map((approval) => <button className={`approval-row ${selected?.approval_id === approval.approval_id ? 'selected' : ''}`} key={approval.approval_id} onClick={() => setSelectedId(approval.approval_id)} type="button"><div className={`severity-line ${approval.finding.severity}`} /><div className="approval-main"><div className="approval-title"><strong>{approval.plan.summary}</strong><span className={`status-chip ${approval.status}`}>{approval.status}</span></div><div className="approval-context"><span>{approval.finding.rule_id}</span><span>•</span><span>{approval.finding.device_id}</span></div></div><div className="approval-time">{approval.approval_id.slice(-8)}<ArrowUpRight size={15} /></div></button>)}</div>
              {!scenario && <div className="empty-state"><Network size={22} /><p>Run an audit to load real approval requests from the API.</p></div>}
              {scenario && <div className="scenario-footer"><span>{approvedCount}/{approvals.length} approved</span><span>{scenario.live ? 'Execution complete' : readyToExecute ? 'Ready to execute' : 'Review required'}</span></div>}
            </div>
            {selected && <div className="panel detail-panel"><div className="detail-top"><div><span className="section-kicker">REMEDIATION REQUEST</span><div className="request-id">{selected.approval_id.slice(-12)} <span className={`status-chip ${selected.status}`}>{selected.status}</span></div></div></div><div className="device-line"><div className="device-icon"><Network size={17} /></div><div><strong>{selected.finding.device_id}</strong><span>Virtual Lab</span></div><span className={`severity-label ${selected.finding.severity}`}><CircleAlert size={14} /> {selected.finding.severity} risk</span></div><div className="finding-block"><span>Finding</span><p>Expected: {selected.finding.expected}<br />Evidence: {selected.finding.evidence.join(', ') || 'No evidence returned'}</p></div><div className="command-block"><div className="command-header"><span>Proposed commands</span><code>scope: {selected.plan.commands.map((command) => command.scope).join(', ')}</code></div><div className="terminal"><div className="terminal-bar"><i /><i /><i /><span>ios-config</span></div>{selected.plan.commands.map((command) => <div className="command-line" key={`${selected.approval_id}-${command.command}`}><span>$</span>{command.command}</div>)}</div></div><div className="detail-footer"><div><span>Generated by</span><strong>{selected.plan.model_metadata.provider} / {selected.plan.model_metadata.model}</strong></div>{selected.status === 'pending' ? <div className="decision-actions"><button className="reject-button" disabled={busy} onClick={() => decide('reject')} type="button"><X size={16} />Reject</button><button className="approve-button" disabled={busy} onClick={() => decide('approve')} type="button"><Check size={16} />Approve plan</button></div> : <div className="decision-complete"><CircleCheck size={16} />Decision recorded</div>}</div></div>}
          </section>
          {scenario?.live && <div className={`result-banner ${scenario.live.reaudit.remediation_succeeded ? 'success' : 'failure'}`}><CircleCheck size={17} />{scenario.live.reaudit.remediation_succeeded ? 'Scenario passed post-change re-audit.' : 'Scenario failed post-change re-audit.'}</div>}
          {notice && <div className="toast"><CircleCheck size={17} />{notice}</div>}
        </div>
      </main>
    </div>
  )
}

export default App
