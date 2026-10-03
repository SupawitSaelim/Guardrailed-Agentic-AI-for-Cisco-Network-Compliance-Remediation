import { useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  Activity,
  ArrowUpRight,
  Check,
  ChevronDown,
  CircleAlert,
  CircleCheck,
  Clock3,
  Command,
  FileClock,
  LayoutDashboard,
  Network,
  PanelLeft,
  Search,
  ShieldCheck,
  X,
} from 'lucide-react'
import './App.css'

type ApprovalStatus = 'pending' | 'approved' | 'rejected'
type Severity = 'High' | 'Medium' | 'Low'

type Approval = {
  id: string
  device: string
  location: string
  rule: string
  severity: Severity
  status: ApprovalStatus
  age: string
  finding: string
  commands: string[]
  scope: string
  model: string
}

const initialApprovals: Approval[] = [
  {
    id: 'APR-2048',
    device: 'core-rtr-01',
    location: 'Bangkok / Lab A',
    rule: 'Approved NTP server',
    severity: 'High',
    status: 'pending',
    age: '12 min ago',
    finding: 'NTP points to 10.10.10.20. Policy requires 10.10.10.10.',
    commands: ['no ntp server 10.10.10.20', 'ntp server 10.10.10.10'],
    scope: 'ntp',
    model: 'mock / deterministic-test-model',
  },
  {
    id: 'APR-2047',
    device: 'edge-sw-03',
    location: 'Bangkok / Lab B',
    rule: 'HTTP server disabled',
    severity: 'Medium',
    status: 'pending',
    age: '34 min ago',
    finding: 'HTTP server is enabled on the device.',
    commands: ['no ip http server'],
    scope: 'ip http',
    model: 'mock / deterministic-test-model',
  },
  {
    id: 'APR-2046',
    device: 'dist-rtr-02',
    location: 'Chiang Mai / Lab C',
    rule: 'SSH version 2',
    severity: 'Low',
    status: 'approved',
    age: '1 hr ago',
    finding: 'SSH version 1 is configured.',
    commands: ['ip ssh version 2'],
    scope: 'ip ssh',
    model: 'mock / deterministic-test-model',
  },
]

const navItems: { label: string; icon: LucideIcon }[] = [
  { label: 'Overview', icon: LayoutDashboard },
  { label: 'Approvals', icon: CircleCheck },
  { label: 'Devices', icon: Network },
  { label: 'Audit logs', icon: FileClock },
  { label: 'Experiments', icon: Activity },
]

function App() {
  const [approvals, setApprovals] = useState(initialApprovals)
  const [selectedId, setSelectedId] = useState(initialApprovals[0].id)
  const [activeView, setActiveView] = useState('Approvals')
  const [notice, setNotice] = useState('')

  const selected = approvals.find((approval) => approval.id === selectedId)
  const pendingCount = approvals.filter((approval) => approval.status === 'pending').length
  const approvedCount = approvals.filter((approval) => approval.status === 'approved').length

  const decide = (status: ApprovalStatus) => {
    if (!selected || selected.status !== 'pending') return
    setApprovals((current) => current.map((approval) =>
      approval.id === selected.id ? { ...approval, status } : approval,
    ))
    setNotice(`${selected.id} marked ${status}.`)
    window.setTimeout(() => setNotice(''), 2600)
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><ShieldCheck size={18} strokeWidth={2.4} /></div>
          <div><strong>Sentinel</strong><span>Network control plane</span></div>
        </div>
        <div className="workspace-switcher">
          <div className="workspace-dot" />
          <div><span>Workspace</span><strong>Virtual Lab</strong></div>
          <ChevronDown size={15} />
        </div>
        <nav className="nav-list" aria-label="Primary navigation">
          {navItems.map(({ label, icon: Icon }) => (
            <button className={`nav-item ${activeView === label ? 'active' : ''}`} key={label} onClick={() => setActiveView(label)} type="button">
              <Icon size={17} />
              <span>{label}</span>
              {label === 'Approvals' && <b>{pendingCount}</b>}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="system-status"><span className="status-pulse" />All systems operational</div>
          <div className="user-row"><div className="avatar">AK</div><div><strong>Alex Kim</strong><span>Operator</span></div><PanelLeft size={16} /></div>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div className="mobile-brand"><div className="brand-mark"><ShieldCheck size={18} /></div><strong>Sentinel</strong></div>
          <div className="breadcrumbs"><span>Workspace</span><span>/</span><strong>{activeView}</strong></div>
          <div className="top-actions"><button className="icon-button" title="Search" aria-label="Search"><Search size={18} /></button><div className="top-avatar">AK</div></div>
        </header>

        <div className="content-wrap">
          <section className="page-heading">
            <div><p className="eyebrow">CONTROL CENTER <span>•</span> OCT 03, 2026</p><h1>{activeView}</h1><p className="subheading">Review proposed network changes before they reach your lab.</p></div>
            <div className="heading-meta"><span className="live-dot" />Live monitoring</div>
          </section>

          <section className="stat-grid" aria-label="Compliance summary">
            <div className="stat-card"><div className="stat-icon orange"><Clock3 size={17} /></div><span>Awaiting approval</span><strong>{pendingCount}</strong><small>Requires your attention</small></div>
            <div className="stat-card"><div className="stat-icon green"><CircleCheck size={17} /></div><span>Approved today</span><strong>{approvedCount}</strong><small className="positive">+12% <em>vs yesterday</em></small></div>
            <div className="stat-card"><div className="stat-icon blue"><Network size={17} /></div><span>Lab devices</span><strong>12</strong><small>All reachable</small></div>
            <div className="stat-card"><div className="stat-icon slate"><Activity size={17} /></div><span>Compliance score</span><strong>96.8<sup>%</sup></strong><small className="positive">+2.4% <em>this week</em></small></div>
          </section>

          <section className="dashboard-grid">
            <div className="panel queue-panel">
              <div className="panel-heading"><div><span className="section-kicker">REVIEW QUEUE</span><h2>Pending approvals <span className="count-pill">{pendingCount}</span></h2></div><button className="filter-button" type="button">All severities <ChevronDown size={14} /></button></div>
              <div className="approval-list">
                {approvals.map((approval) => (
                  <button className={`approval-row ${selected?.id === approval.id ? 'selected' : ''}`} key={approval.id} onClick={() => setSelectedId(approval.id)} type="button">
                    <div className={`severity-line ${approval.severity.toLowerCase()}`} />
                    <div className="approval-main"><div className="approval-title"><strong>{approval.rule}</strong><span className={`status-chip ${approval.status}`}>{approval.status}</span></div><div className="approval-context"><span>{approval.device}</span><span>•</span><span>{approval.location}</span></div></div>
                    <div className="approval-time">{approval.age}<ArrowUpRight size={15} /></div>
                  </button>
                ))}
              </div>
              <button className="view-all" type="button" onClick={() => setNotice('All approvals are already visible in this mock queue.')}>View full approval history <ArrowUpRight size={15} /></button>
            </div>

            {selected && <div className="panel detail-panel">
              <div className="detail-top"><div><span className="section-kicker">REMEDIATION REQUEST</span><div className="request-id">{selected.id} <span className={`status-chip ${selected.status}`}>{selected.status === 'pending' ? 'Awaiting review' : `${selected.status} by you`}</span></div></div><button className="icon-button" title="More actions" aria-label="More actions"><Command size={18} /></button></div>
              <div className="device-line"><div className="device-icon"><Network size={17} /></div><div><strong>{selected.device}</strong><span>{selected.location}</span></div><span className={`severity-label ${selected.severity.toLowerCase()}`}><CircleAlert size={14} /> {selected.severity} risk</span></div>
              <div className="finding-block"><span>Finding</span><p>{selected.finding}</p></div>
              <div className="command-block"><div className="command-header"><span>Proposed commands</span><code>scope: {selected.scope}</code></div><div className="terminal"><div className="terminal-bar"><i /><i /><i /><span>ios-config</span></div>{selected.commands.map((command) => <div className="command-line" key={command}><span>$</span>{command}</div>)}</div></div>
              <div className="detail-footer"><div><span>Generated by</span><strong>{selected.model}</strong></div>{selected.status === 'pending' ? <div className="decision-actions"><button className="reject-button" type="button" onClick={() => decide('rejected')}><X size={16} />Reject</button><button className="approve-button" type="button" onClick={() => decide('approved')}><Check size={16} />Approve change</button></div> : <div className="decision-complete"><CircleCheck size={16} />Decision recorded</div>}</div>
            </div>}
          </section>
          {notice && <div className="toast"><CircleCheck size={17} />{notice}</div>}
        </div>
      </main>
    </div>
  )
}

export default App
