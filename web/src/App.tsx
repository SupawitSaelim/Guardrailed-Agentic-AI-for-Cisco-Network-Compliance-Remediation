import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Terminal as XTerm } from '@xterm/xterm'
import '@xterm/xterm/css/xterm.css'
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
  Plus,
  Search,
  Server,
  ShieldCheck,
  Terminal,
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
  target: { device_id: string; host: string; device_type: string }
  workflow: {
    status: string
    findings: Finding[]
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

type Finding = {
  finding_id: string
  rule_id: string
  severity: Severity
  expected: string
  actual: string[]
  evidence: string[]
  allowed_scope: string[]
}

type RemediationPrompt = {
  instruction: string
  finding: Finding
  configuration_context: string
  allowed_scope: string[]
  output_schema: object
}

type BatchExecutionResult = {
  executed_count: number
  skipped_count: number
  failed_count: number
  results: { scenario_id: string; device_id: string; status: 'executed' | 'skipped' | 'failed'; detail?: string | null }[]
}

type BatchAuditResult = {
  audited_count: number
  failed_count: number
  results: { device_id: string; scenario_id: string; status: 'audited' | 'failed'; detail?: string | null }[]
}

type CredentialStatus = {
  configured: boolean
  username: string | null
  port: number
}

const API_BASE = '/api'
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

type Device = {
  device_id: string
  target: { device_id: string; host: string; device_type: string }
  credential_profile: string
  status: 'registered' | 'reachable' | 'unreachable'
  last_audit_scenario_id: string | null
  last_audit_status: string | null
}

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
  const [prompt, setPrompt] = useState<RemediationPrompt | null>(null)
  const [chatbotResponse, setChatbotResponse] = useState('')
  const [devices, setDevices] = useState<Device[]>([])
  const [terminalDevice, setTerminalDevice] = useState<Device | null>(null)
  const xtermContainerRef = useRef<HTMLDivElement>(null)
  const xtermRef = useRef<XTerm | null>(null)
  const terminalSocketRef = useRef<WebSocket | null>(null)
  const [credentialForm, setCredentialForm] = useState({ username: '', password: '', secret: '', port: '22' })
  const [editingDeviceId, setEditingDeviceId] = useState<string | null>(null)
  const [deviceForm, setDeviceForm] = useState({
    device_id: '',
    host: '',
    device_type: 'cisco_ios',
    credential_profile: '',
    username: '',
    password: '',
    secret: '',
  })
  const terminalDeviceId = new URLSearchParams(window.location.search).get('device_id')
  const isTerminalPage = window.location.pathname === '/terminal'

  const approvals = scenario?.workflow.approvals ?? []
  const selected = approvals.find((approval) => approval.approval_id === selectedId) ?? approvals[0]
  const pendingCount = approvals.filter((approval) => approval.status === 'pending').length
  const approvedCount = approvals.filter((approval) => approval.status === 'approved').length
  const readyToExecute = approvals.length > 0 && pendingCount === 0 && !scenario?.live
  const loadDevices = async (): Promise<Device[]> => {
    try {
      const loaded = await request<Device[]>('/devices')
      setDevices(loaded)
      return loaded
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not load inventory')
      return []
    }

  }

  const loadCredentials = async () => {
    try {
      const credentials = await request<CredentialStatus>('/settings/credentials')
      setCredentialForm((current) => ({ ...current, username: credentials.username ?? '', port: String(credentials.port) }))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not load global SSH settings')
    }
  }

  const showNotice = (message: string) => {
    setNotice(message)
    window.setTimeout(() => setNotice(''), 2800)
  }

  const auditDevice = async (device: Device) => {
    setBusy(true)
    setError('')
    try {
      const next = await request<Scenario>(`/devices/${device.device_id}/audit`, {
        method: 'POST',
        body: JSON.stringify({
          scenario_id: `audit-${device.device_id}-${Date.now()}`,
          rules,
          requested_by: 'operator-01',
        }),
      })
      setScenario(next)
      setSelectedId(next.workflow.approvals[0]?.approval_id ?? '')
      setActiveView('Approvals')
      showNotice(`Audit complete for ${device.device_id}.`)
      await loadDevices()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Live audit failed')
      await loadDevices()
    } finally {
      setBusy(false)
    }
  }

  const registerDevice = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await request<Device>('/devices', {
        method: 'POST',
        body: JSON.stringify({
          device_id: deviceForm.device_id,
          host: deviceForm.host,
          device_type: deviceForm.device_type,
        }),
      })
      setDeviceForm({ device_id: '', host: '', device_type: 'cisco_ios', credential_profile: '', username: '', password: '', secret: '' })
      await loadDevices()
      showNotice('Lab device registered.')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Device registration failed')
    } finally {
      setBusy(false)
    }

  }

  const editDevice = (device: Device) => {
    setEditingDeviceId(device.device_id)
    setDeviceForm({
      device_id: device.device_id,
      host: device.target.host,
      device_type: device.target.device_type,
      credential_profile: '',
      username: '',
      password: '',
      secret: '',
    })
  }

  const saveDevice = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!editingDeviceId) return
    setBusy(true)
    setError('')
    try {
      await request<Device>(`/devices/${encodeURIComponent(editingDeviceId)}`, {
        method: 'PUT',
        body: JSON.stringify({
          device_id: deviceForm.device_id,
          host: deviceForm.host,
          device_type: deviceForm.device_type,
        }),
      })
      setEditingDeviceId(null)
      setDeviceForm({ device_id: '', host: '', device_type: 'cisco_ios', credential_profile: '', username: '', password: '', secret: '' })
      await loadDevices()
      showNotice('Device details updated.')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Device update failed')
    } finally {
      setBusy(false)
    }
  }

  const cancelDeviceEdit = () => {
    setEditingDeviceId(null)
    setDeviceForm({ device_id: '', host: '', device_type: 'cisco_ios', credential_profile: '', username: '', password: '', secret: '' })
  }

  const saveCredentials = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await request<CredentialStatus>('/settings/credentials', {
        method: 'PUT',
        body: JSON.stringify({ ...credentialForm, port: Number(credentialForm.port) }),
      })
      setCredentialForm((current) => ({ ...current, password: '', secret: '' }))
      showNotice('Global SSH credentials saved.')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not save global SSH settings')
    } finally {
      setBusy(false)
    }

  }

  const openTerminal = (device: Device) => {
    window.open(
      `/terminal?device_id=${encodeURIComponent(device.device_id)}`,
      '_blank',
      'noopener,noreferrer',
    )
  }

  useEffect(() => {
    if (!isTerminalPage || !terminalDeviceId) return
    void request<Device>(`/devices/${encodeURIComponent(terminalDeviceId)}`)
      .then(setTerminalDevice)
      .catch(() => xtermRef.current?.writeln('[Device not found]'))
  }, [isTerminalPage, terminalDeviceId])

  useEffect(() => {
    if (!isTerminalPage || !terminalDevice) return
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const socket = new WebSocket(`${protocol}//${window.location.host}/api/devices/${encodeURIComponent(terminalDevice.device_id)}/terminal`)
    terminalSocketRef.current = socket
    socket.addEventListener('open', () => xtermRef.current?.focus())
    socket.addEventListener('message', (event) => {
      const message = JSON.parse(event.data) as { type: string; data?: string; message?: string }
      if (message.data) xtermRef.current?.write(message.data)
      else xtermRef.current?.writeln(`[${message.message ?? message.type}]`)
    })
    socket.addEventListener('error', () => xtermRef.current?.writeln('[Connection error]'))
    socket.addEventListener('close', () => xtermRef.current?.writeln('[Disconnected]'))
    return () => {
      socket.close()
      terminalSocketRef.current = null
    }
  }, [isTerminalPage, terminalDevice])

  useEffect(() => {
    if (!isTerminalPage || !xtermContainerRef.current) return
    const terminal = new XTerm({ convertEol: true, cursorBlink: true, theme: { background: '#10171b', foreground: '#d6e4dc' } })
    terminal.open(xtermContainerRef.current)
    terminal.onData((data) => {
      if (terminalSocketRef.current?.readyState === WebSocket.OPEN) terminalSocketRef.current.send(data)
    })
    xtermRef.current = terminal
    return () => {
      terminal.dispose()
      xtermRef.current = null
    }
  }, [isTerminalPage])

  if (isTerminalPage) {
    return <main className="terminal-page"><div className="web-terminal terminal-window"><div className="terminal-heading"><strong>SSH · {terminalDevice?.device_id ?? terminalDeviceId ?? 'Connecting'}</strong><button className="filter-button" onClick={() => window.close()} type="button"><X size={14} />Close</button></div><div ref={xtermContainerRef} className="xterm-screen" /><div className="terminal-help">Interactive console · type directly · Enter sends immediately · Ctrl+C interrupts</div></div></main>
  }

  const runAudit = async () => {
    const availableDevices = devices.length > 0 ? devices : await loadDevices()
    if (availableDevices.length === 0) {
      setActiveView('Devices')
      setError('Register a lab device before running an audit.')
      return
    }
    setBusy(true)
    setError('')
    try {
      const result = await request<BatchAuditResult>('/devices/audit-all', {
        method: 'POST',
        body: JSON.stringify({
          scenario_id: `audit-${Date.now()}`,
          rules,
          requested_by: 'operator-01',
        }),
      })
      const firstAudited = result.results.find((item) => item.status === 'audited')
      if (firstAudited) {
        setScenario(await request<Scenario>(`/scenarios/${firstAudited.scenario_id}`))
        setActiveView('Approvals')
      }
      showNotice(`Audit complete for ${result.audited_count} device(s); ${result.failed_count} failed.`)
      await loadDevices()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Live audit failed')
      await loadDevices()
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

  const executeAll = async () => {
    setBusy(true)
    setError('')
    try {
      const result = await request<BatchExecutionResult>('/scenarios/execute-all', {
        method: 'POST',
      })
      const failed = result.results.filter((item) => item.status === 'failed')
      const detail = failed.length > 0 ? ` Failed: ${failed.map((item) => `${item.device_id} (${item.detail})`).join(', ')}` : ''
      showNotice(`Executed ${result.executed_count} device(s); skipped ${result.skipped_count}.${detail}`)
      if (scenario && result.results.some((item) => item.scenario_id === scenario.scenario_id && item.status === 'executed')) {
        const refreshed = await request<Scenario>(`/scenarios/${scenario.scenario_id}`)
        setScenario(refreshed)
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Batch execution failed')
    } finally {
      setBusy(false)
    }
  }

  const loadPrompt = async () => {
    if (!scenario) return
    try {
      const next = await request<RemediationPrompt>(
        `/scenarios/${scenario.scenario_id}/remediation-prompt`,
      )
      setPrompt(next)
      return next
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not create chatbot prompt')
      return null
    }
  }

  const copyPrompt = async () => {
    const next = await loadPrompt()
    if (next) {
      await navigator.clipboard.writeText(JSON.stringify(next, null, 2))
      showNotice('Prompt copied for the chatbot.')
    }
  }

  const submitChatbotResponse = async () => {
    if (!scenario) return
    setBusy(true)
    setError('')
    try {
      const updated = await request<Scenario>(
        `/scenarios/${scenario.scenario_id}/remediation-response`,
        { method: 'POST', body: chatbotResponse },
      )
      setScenario(updated)
      setSelectedId(updated.workflow.approvals[0]?.approval_id ?? '')
      setChatbotResponse('')
      showNotice('Response passed validation and is ready for approval.')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Chatbot response was rejected')
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
          {navItems.map(({ label, icon: Icon }) => <button className={`nav-item ${activeView === label ? 'active' : ''}`} key={label} onClick={() => { setActiveView(label); if (label === 'Devices') { void loadDevices(); void loadCredentials() } }} type="button"><Icon size={17} /><span>{label}</span>{label === 'Approvals' && <b>{pendingCount}</b>}</button>)}
        </nav>
        <div className="sidebar-bottom"><div className="system-status"><span className="status-pulse" />API control plane</div><div className="user-row"><div className="avatar">AK</div><div><strong>Alex Kim</strong><span>Operator</span></div><PanelLeft size={16} /></div></div>
      </aside>
      <main className="main-content">
        <header className="topbar"><div className="mobile-brand"><div className="brand-mark"><ShieldCheck size={18} /></div><strong>Sentinel</strong></div><div className="breadcrumbs"><span>Workspace</span><span>/</span><strong>{activeView}</strong></div><div className="top-actions"><button className="icon-button" title="Search" aria-label="Search" type="button"><Search size={18} /></button><div className="top-avatar">AK</div></div></header>
        <div className="content-wrap">
          <section className="page-heading"><div><p className="eyebrow">CONTROL CENTER <span>•</span> OCT 03, 2026</p><h1>{activeView}</h1><p className="subheading">Review proposed network changes before they reach your lab.</p></div><button className="approve-button audit-button" disabled={busy} onClick={runAudit} type="button">{busy ? <LoaderCircle className="spin" size={16} /> : <Activity size={16} />}Run audit</button></section>
          {error && <div className="error-banner"><CircleAlert size={17} />{error}</div>}
          {activeView === 'Devices' ? <section className="inventory-layout">
            <div className="panel inventory-form-panel">
              <div className="panel-heading"><div><span className="section-kicker">LAB INVENTORY</span><h2>Add device</h2></div><Server size={20} /></div>
              <form className="device-form" onSubmit={editingDeviceId ? saveDevice : registerDevice}>
                <label>Device ID<input required value={deviceForm.device_id} onChange={(event) => setDeviceForm({ ...deviceForm, device_id: event.target.value })} placeholder="lab-router-01" /></label>
                <label>IP address / hostname<input required value={deviceForm.host} onChange={(event) => setDeviceForm({ ...deviceForm, host: event.target.value })} placeholder="192.0.2.10" /></label>
                <label>Device type<select value={deviceForm.device_type} onChange={(event) => setDeviceForm({ ...deviceForm, device_type: event.target.value })}><option value="cisco_ios">Cisco IOS</option><option value="cisco_xe">Cisco IOS XE</option></select></label>
                <p className="form-help">SSH credentials are configured once in the Global SSH settings panel and used for every lab device.</p>
                <div className="form-actions"><button className="approve-button audit-button" disabled={busy} type="submit">{editingDeviceId ? <Check size={16} /> : <Plus size={16} />}{editingDeviceId ? 'Save device changes' : 'Add lab device'}</button>{editingDeviceId && <button className="filter-button" disabled={busy} onClick={cancelDeviceEdit} type="button">Cancel</button>}</div>
              </form>
            </div>
            <div className="panel inventory-form-panel">
              <div className="panel-heading"><div><span className="section-kicker">GLOBAL SSH SETTINGS</span><h2>Connection credentials</h2></div><Server size={20} /></div>
              <form className="device-form" onSubmit={saveCredentials}>
                <label>Username<input required autoComplete="username" value={credentialForm.username} onChange={(event) => setCredentialForm({ ...credentialForm, username: event.target.value })} placeholder="admin" /></label>
                <label>Password<input required type="password" autoComplete="current-password" value={credentialForm.password} onChange={(event) => setCredentialForm({ ...credentialForm, password: event.target.value })} placeholder="Enter to update" /></label>
                <label>Enable secret <span className="optional-label">(optional)</span><input type="password" autoComplete="off" value={credentialForm.secret} onChange={(event) => setCredentialForm({ ...credentialForm, secret: event.target.value })} placeholder="Optional" /></label>
                <label>SSH port<input required type="number" min="1" max="65535" value={credentialForm.port} onChange={(event) => setCredentialForm({ ...credentialForm, port: event.target.value })} /></label>
                <p className="form-help">Saved in the local Lab JSON database and never returned to the device list.</p>
                <button className="approve-button audit-button" disabled={busy} type="submit"><Check size={16} />Save global SSH settings</button>
              </form>
            </div>
            <div className="panel inventory-list-panel">
              <div className="panel-heading"><div><span className="section-kicker">REGISTERED DEVICES</span><h2>Virtual Lab <span className="count-pill">{devices.length}</span></h2></div><div className="panel-actions"><button className="filter-button" onClick={loadDevices} type="button">Refresh</button><button className="execute-button compact" disabled={busy || devices.length === 0} onClick={executeAll} type="button"><ArrowUpRight size={15} />Execute all approved</button></div></div>
              <div className="device-table">{devices.map((device) => <div className="device-card" key={device.device_id}><div className="device-card-icon"><Network size={18} /></div><div className="device-card-main"><strong>{device.device_id}</strong><span>{device.target.host} · {device.target.device_type}</span><small>Credential profile: {device.credential_profile}</small></div><span className={`inventory-status ${device.status}`}>{device.status}</span><button className="filter-button" disabled={busy} onClick={() => editDevice(device)} type="button">Edit</button><button className="filter-button" disabled={busy} onClick={() => openTerminal(device)} type="button"><Terminal size={14} />SSH</button><button className="approve-button audit-button" disabled={busy} onClick={() => auditDevice(device)} type="button"><Activity size={15} />Audit</button></div>)}</div>
              {devices.length === 0 && <div className="empty-state"><Server size={22} /><p>No lab devices registered yet. Add a device to start a live audit.</p></div>}
            </div>
          </section> : scenario?.workflow.status === 'awaiting_remediation' ? <section className="manual-remediation panel">
            <div className="panel-heading"><div><span className="section-kicker">MANUAL CHATBOT MODE</span><h2>Remediation needed</h2></div><Activity size={20} /></div>
            <div className="manual-finding"><strong>{scenario.workflow.findings[0]?.rule_id}</strong><span>{scenario.workflow.findings[0]?.severity} risk</span><p>Expected: {scenario.workflow.findings[0]?.expected}<br />Found: {scenario.workflow.findings[0]?.actual.join(', ') || 'No matching configuration'}</p></div>
            <div className="manual-actions"><button className="approve-button audit-button" onClick={copyPrompt} type="button"><ArrowUpRight size={15} />Copy prompt for chatbot</button><button className="filter-button" onClick={loadPrompt} type="button">Preview prompt</button></div>
            {prompt && <pre className="prompt-preview">{JSON.stringify(prompt, null, 2)}</pre>}
            <label className="response-label">Paste chatbot JSON response<textarea value={chatbotResponse} onChange={(event) => setChatbotResponse(event.target.value)} placeholder={'{\n  "summary": "...",\n  "commands": [],\n  "assumptions": []\n}'} /></label>
            <button className="approve-button audit-button submit-response" disabled={busy || !chatbotResponse.trim()} onClick={submitChatbotResponse} type="button"><Check size={15} />Validate response</button>
          </section> :
          <section className="stat-grid" aria-label="Scenario summary">
            <div className="stat-card"><div className="stat-icon orange"><Clock3 size={17} /></div><span>Awaiting approval</span><strong>{pendingCount}</strong><small>Scenario plans pending</small></div>
            <div className="stat-card"><div className="stat-icon green"><CircleCheck size={17} /></div><span>Approved plans</span><strong>{approvedCount}</strong><small>{scenario ? `${approvals.length} total plans` : 'Run an audit to begin'}</small></div>
            <div className="stat-card"><div className="stat-icon blue"><Network size={17} /></div><span>Scenario device</span><strong>{scenario ? scenario.target.device_id : '—'}</strong><small>{scenario?.target.host ?? 'Virtual lab target'}</small></div>
            <div className="stat-card"><div className="stat-icon slate"><Activity size={17} /></div><span>Re-audit</span><strong>{scenario?.live ? (scenario.live.reaudit.post_compliant ? 'PASS' : 'FAIL') : '—'}</strong><small>{scenario?.live ? 'Post-check completed' : 'Not executed'}</small></div>
          </section>}
          <section className="dashboard-grid">
            <div className="panel queue-panel">
              <div className="panel-heading"><div><span className="section-kicker">SCENARIO REVIEW QUEUE</span><h2>{scenario ? scenario.scenario_id : 'No scenario loaded'} <span className="count-pill">{approvals.length}</span></h2></div></div>
              <div className="approval-list">{approvals.map((approval) => <button className={`approval-row ${selected?.approval_id === approval.approval_id ? 'selected' : ''}`} key={approval.approval_id} onClick={() => setSelectedId(approval.approval_id)} type="button"><div className={`severity-line ${approval.finding.severity}`} /><div className="approval-main"><div className="approval-title"><strong>{approval.plan.summary}</strong><span className={`status-chip ${approval.status}`}>{approval.status}</span></div><div className="approval-context"><span>{approval.finding.rule_id}</span><span>•</span><span>{approval.finding.device_id}</span></div></div><div className="approval-time">{approval.approval_id.slice(-8)}<ArrowUpRight size={15} /></div></button>)}</div>
              {!scenario && <div className="empty-state"><Network size={22} /><p>Run an audit to load real approval requests from the API.</p></div>}
              {scenario && <div className="scenario-footer"><span>{approvedCount}/{approvals.length} approved</span><span>{scenario.live ? 'Execution complete' : readyToExecute ? 'Ready to execute' : 'Review required'}</span></div>}
              {readyToExecute && <button className="execute-button" disabled={busy} onClick={execute} type="button"><ArrowUpRight size={17} />Send approved commands to {scenario?.target.device_id}</button>}
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
