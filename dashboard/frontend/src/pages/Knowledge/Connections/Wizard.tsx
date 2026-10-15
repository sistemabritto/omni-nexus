// Modified 2026-10-15: OmniNexus Live global UI system; original EvoNexus attribution retained.
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X, CheckCircle, XCircle, RefreshCw, Database } from 'lucide-react'
import { api } from '../../../lib/api'
import { useKnowledge } from '../../../context/KnowledgeContext'

interface Props {
  onClose: () => void
  onCreated: () => Promise<void>
}

type Step = 1 | 2 | 3

interface FormData {
  name: string
  slug: string
  host: string
  port: string
  username: string
  password: string
  database_name: string
  ssl_mode: string
  connection_string: string
  useConnectionString: boolean
}

interface ConfigPhase {
  label: string
  status: 'pending' | 'running' | 'done' | 'error'
  error?: string
}

const defaultPhases: ConfigPhase[] = [
  { label: 'Connecting to Postgres', status: 'pending' },
  { label: 'Validating pgvector extension', status: 'pending' },
  { label: 'Applying schema migrations', status: 'pending' },
  { label: 'Creating default space', status: 'pending' },
]

export default function Wizard({ onClose, onCreated }: Props) {
  const { t } = useTranslation()
  const { refreshConnections } = useKnowledge()
  const [step, setStep] = useState<Step>(1)
  const [form, setForm] = useState<FormData>({
    name: '',
    slug: '',
    host: '',
    port: '5432',
    username: '',
    password: '',
    database_name: '',
    ssl_mode: 'require',
    connection_string: '',
    useConnectionString: false,
  })
  const [phases, setPhases] = useState<ConfigPhase[]>(defaultPhases.map((p) => ({ ...p })))
  const [configuring, setConfiguring] = useState(false)
  const [configError, setConfigError] = useState<string | null>(null)
  const [createdId, setCreatedId] = useState<string | null>(null)

  function set(key: keyof FormData, value: string | boolean) {
    setForm((prev) => ({ ...prev, [key]: value }))
    // Auto-generate slug from name
    if (key === 'name' && typeof value === 'string') {
      setForm((prev) => ({
        ...prev,
        name: value,
        slug: value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''),
      }))
    }
  }

  async function handleConfigure() {
    if (!form.name || !form.slug) {
      setConfigError('Name and slug are required')
      return
    }
    if (!form.useConnectionString && !form.host) {
      setConfigError('Host is required')
      return
    }
    if (!form.useConnectionString && !form.username) {
      setConfigError('Username is required')
      return
    }
    if (form.useConnectionString && !form.connection_string) {
      setConfigError('Connection string is required')
      return
    }

    setConfiguring(true)
    setConfigError(null)
    setStep(2)

    const phasesCopy = defaultPhases.map((p) => ({ ...p }))
    phasesCopy[0] = { ...phasesCopy[0], status: 'running' }
    setPhases([...phasesCopy])

    // Step 1: Create connection record
    let id: string
    try {
      const body: Record<string, unknown> = {
        name: form.name,
        slug: form.slug,
      }
      if (form.useConnectionString) {
        body.connection_string = form.connection_string
      } else {
        body.host = form.host
        body.port = form.port ? parseInt(form.port) : 5432
        body.username = form.username
        body.database_name = form.database_name
        body.ssl_mode = form.ssl_mode
        // Build connection string from fields
        const pw = form.password ? `:${encodeURIComponent(form.password)}` : ''
        const ssl = form.ssl_mode !== 'disable' ? `?sslmode=${form.ssl_mode}` : ''
        const port = form.port || '5432'
        body.connection_string = `postgresql://${form.username}${pw}@${form.host}:${port}/${form.database_name}${ssl}`
      }
      const result = await api.post('/knowledge/connections', body)
      id = result.id
      setCreatedId(id)
      phasesCopy[0] = { ...phasesCopy[0], status: 'done' }
      setPhases([...phasesCopy])
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to create connection'
      phasesCopy[0] = { ...phasesCopy[0], status: 'error', error: msg }
      setPhases([...phasesCopy])
      setConfigError(`Connection failed: ${msg}`)
      setConfiguring(false)
      return
    }

    // Step 2-4: Configure (runs migrations + validates pgvector)
    phasesCopy[1] = { ...phasesCopy[1], status: 'running' }
    phasesCopy[2] = { ...phasesCopy[2], status: 'running' }
    setPhases([...phasesCopy])

    try {
      const result = await api.post(`/knowledge/connections/${id}/configure`)
      if (result.status === 'ready') {
        phasesCopy[1] = { ...phasesCopy[1], status: 'done' }
        phasesCopy[2] = { ...phasesCopy[2], status: 'done' }
        phasesCopy[3] = { ...phasesCopy[3], status: 'done' }
        setPhases([...phasesCopy])
        await refreshConnections()
        setStep(3)
      } else {
        const errMsg = result.message || result.error || 'Configuration failed'
        phasesCopy[1] = { ...phasesCopy[1], status: 'error', error: errMsg }
        phasesCopy[2] = { ...phasesCopy[2], status: 'error' }
        phasesCopy[3] = { ...phasesCopy[3], status: 'error' }
        setPhases([...phasesCopy])
        setConfigError(errMsg)
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Configuration failed'
      phasesCopy[1] = { ...phasesCopy[1], status: 'error', error: msg }
      phasesCopy[2] = { ...phasesCopy[2], status: 'error' }
      phasesCopy[3] = { ...phasesCopy[3], status: 'error' }
      setPhases([...phasesCopy])
      setConfigError(`Configuration failed: ${msg}`)
    }

    setConfiguring(false)
  }

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
      <div className="bg-[color:var(--bg-primary)] border border-[color:var(--border)] rounded-xl w-full max-w-lg shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[color:var(--border)]">
          <div className="flex items-center gap-2">
            <Database size={16} className="text-[color:var(--evo-green)]" />
            <h2 className="text-sm font-semibold text-[color:var(--text-primary)]">{t('knowledge.newConnection')}</h2>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg text-[color:var(--text-muted)] hover:text-[color:var(--text-secondary)] hover:bg-white/5 transition-colors">
            <X size={16} />
          </button>
        </div>

        {/* Step indicators */}
        <div className="flex items-center gap-2 px-6 py-3 border-b border-[color:var(--border)]">
          {[1, 2, 3].map((s) => (
            <div key={s} className="flex items-center gap-2">
              <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium ${
                step === s ? 'bg-[color:var(--evo-green)] text-[color:var(--bg-primary)]' :
                step > s ? 'bg-[color:var(--evo-green)]/20 text-[color:var(--evo-green)]' :
                'bg-white/5 text-[color:var(--text-muted)]'
              }`}>{s}</div>
              {s < 3 && <div className={`h-px w-8 ${step > s ? 'bg-[color:var(--evo-green)]/40' : 'bg-[color:var(--border)]'}`} />}
            </div>
          ))}
          <span className="text-xs text-[color:var(--text-muted)] ml-2">
            {step === 1 ? 'Credentials' : step === 2 ? 'Configuring...' : 'Done'}
          </span>
        </div>

        <div className="px-6 py-5">
          {/* Step 1: Credentials */}
          {step === 1 && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div className="col-span-2">
                  <label className="block text-xs text-[color:var(--text-muted)] mb-1">Connection Name *</label>
                  <input
                    type="text"
                    placeholder="e.g. Academy - Supabase"
                    value={form.name}
                    onChange={(e) => set('name', e.target.value)}
                    className="w-full bg-[color:var(--bg-card)] border border-[color:var(--border)] rounded-lg px-3 py-2 text-sm text-[color:var(--text-primary)] placeholder-[#667085] focus:border-[color:var(--evo-green)] focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs text-[color:var(--text-muted)] mb-1">Slug *</label>
                  <input
                    type="text"
                    placeholder="academy-supabase"
                    value={form.slug}
                    onChange={(e) => set('slug', e.target.value)}
                    className="w-full bg-[color:var(--bg-card)] border border-[color:var(--border)] rounded-lg px-3 py-2 text-sm text-[color:var(--text-primary)] placeholder-[#667085] focus:border-[color:var(--evo-green)] focus:outline-none font-mono"
                  />
                </div>
                <div>
                  <label className="block text-xs text-[color:var(--text-muted)] mb-1">SSL Mode</label>
                  <select
                    value={form.ssl_mode}
                    onChange={(e) => set('ssl_mode', e.target.value)}
                    className="w-full bg-[color:var(--bg-card)] border border-[color:var(--border)] rounded-lg px-3 py-2 text-sm text-[color:var(--text-secondary)] focus:border-[color:var(--evo-green)] focus:outline-none"
                  >
                    <option value="disable">disable</option>
                    <option value="require">require</option>
                    <option value="verify-full">verify-full</option>
                  </select>
                </div>
              </div>

              {/* Toggle */}
              <div className="flex items-center gap-2">
                <button
                  onClick={() => set('useConnectionString', !form.useConnectionString)}
                  className="flex items-center gap-2 text-xs text-[color:var(--text-muted)] hover:text-[color:var(--text-secondary)] transition-colors"
                >
                  <div className={`w-8 h-4 rounded-full transition-colors relative ${form.useConnectionString ? 'bg-[color:var(--evo-green)]' : 'bg-[color:var(--border)]'}`}>
                    <div className={`absolute top-0.5 w-3 h-3 rounded-full bg-white transition-transform ${form.useConnectionString ? 'translate-x-4' : 'translate-x-0.5'}`} />
                  </div>
                  Use connection string
                </button>
              </div>

              {form.useConnectionString ? (
                <div>
                  <label className="block text-xs text-[color:var(--text-muted)] mb-1">Connection String *</label>
                  <input
                    type="password"
                    placeholder="postgresql://user:password@host:5432/database"
                    value={form.connection_string}
                    onChange={(e) => set('connection_string', e.target.value)}
                    className="w-full bg-[color:var(--bg-card)] border border-[color:var(--border)] rounded-lg px-3 py-2 text-sm text-[color:var(--text-primary)] placeholder-[#667085] focus:border-[color:var(--evo-green)] focus:outline-none font-mono"
                  />
                  <p className="mt-2 text-[11px] text-[color:var(--text-muted)] leading-relaxed">
                    Using <strong>Supabase / Neon / Railway</strong>? Use the <em>direct</em>{' '}
                    connection string on port <code className="text-[color:var(--text-secondary)]">5432</code>, not the
                    transaction pooler on <code className="text-[color:var(--text-secondary)]">6543</code>. Transaction
                    pooling (PgBouncer) breaks Alembic migrations,{' '}
                    <code className="text-[color:var(--text-secondary)]">CREATE INDEX … USING hnsw</code>, and
                    SQLAlchemy prepared statements. Session pooler works if you need pooling.
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-[color:var(--text-muted)] mb-1">Host *</label>
                    <input
                      type="text"
                      placeholder="db.example.com"
                      value={form.host}
                      onChange={(e) => set('host', e.target.value)}
                      className="w-full bg-[color:var(--bg-card)] border border-[color:var(--border)] rounded-lg px-3 py-2 text-sm text-[color:var(--text-primary)] placeholder-[#667085] focus:border-[color:var(--evo-green)] focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-[color:var(--text-muted)] mb-1">Port</label>
                    <input
                      type="number"
                      placeholder="5432"
                      value={form.port}
                      onChange={(e) => set('port', e.target.value)}
                      className="w-full bg-[color:var(--bg-card)] border border-[color:var(--border)] rounded-lg px-3 py-2 text-sm text-[color:var(--text-primary)] placeholder-[#667085] focus:border-[color:var(--evo-green)] focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-[color:var(--text-muted)] mb-1">Username *</label>
                    <input
                      type="text"
                      placeholder="postgres"
                      value={form.username}
                      onChange={(e) => set('username', e.target.value)}
                      className="w-full bg-[color:var(--bg-card)] border border-[color:var(--border)] rounded-lg px-3 py-2 text-sm text-[color:var(--text-primary)] placeholder-[#667085] focus:border-[color:var(--evo-green)] focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-[color:var(--text-muted)] mb-1">Password</label>
                    <input
                      type="password"
                      placeholder="••••••••"
                      value={form.password}
                      onChange={(e) => set('password', e.target.value)}
                      className="w-full bg-[color:var(--bg-card)] border border-[color:var(--border)] rounded-lg px-3 py-2 text-sm text-[color:var(--text-primary)] placeholder-[#667085] focus:border-[color:var(--evo-green)] focus:outline-none"
                    />
                  </div>
                  <div className="col-span-2">
                    <label className="block text-xs text-[color:var(--text-muted)] mb-1">Database Name</label>
                    <input
                      type="text"
                      placeholder="mydb"
                      value={form.database_name}
                      onChange={(e) => set('database_name', e.target.value)}
                      className="w-full bg-[color:var(--bg-card)] border border-[color:var(--border)] rounded-lg px-3 py-2 text-sm text-[color:var(--text-primary)] placeholder-[#667085] focus:border-[color:var(--evo-green)] focus:outline-none"
                    />
                  </div>
                </div>
              )}

              <div className="bg-[color:var(--bg-card)] border border-[color:var(--border)] rounded-lg px-4 py-3 text-xs text-[color:var(--text-muted)]">
                <strong className="text-[color:var(--text-secondary)]">Prerequisites:</strong> Postgres ≥ 14 with pgvector ≥ 0.5 installed.
                EvoNexus does not provision Postgres — bring your own.
              </div>

              {configError && (
                <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3 text-sm text-red-400">
                  {configError}
                </div>
              )}

              <div className="flex gap-3 pt-2">
                <button onClick={onClose} className="flex-1 px-4 py-2 bg-white/5 text-[color:var(--text-secondary)] rounded-lg text-sm font-medium hover:bg-white/10 transition-colors">
                  Cancel
                </button>
                <button
                  onClick={handleConfigure}
                  disabled={configuring}
                  className="flex-1 px-4 py-2 bg-[color:var(--evo-green)] text-[color:var(--bg-primary)] rounded-lg text-sm font-semibold hover:bg-[color:var(--evo-green)]/90 transition-colors disabled:opacity-50"
                >
                  Connect & Configure
                </button>
              </div>
            </div>
          )}

          {/* Step 2: Configuring */}
          {step === 2 && (
            <div className="space-y-4">
              <p className="text-sm text-[color:var(--text-muted)]">Setting up your connection...</p>
              <div className="space-y-3">
                {phases.map((phase, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <div className="shrink-0">
                      {phase.status === 'pending' && <div className="w-4 h-4 rounded-full bg-white/10" />}
                      {phase.status === 'running' && <RefreshCw size={16} className="text-[color:var(--evo-green)] animate-spin" />}
                      {phase.status === 'done' && <CheckCircle size={16} className="text-[color:var(--evo-green)]" />}
                      {phase.status === 'error' && <XCircle size={16} className="text-red-400" />}
                    </div>
                    <div className="flex-1">
                      <p className={`text-sm ${phase.status === 'error' ? 'text-red-400' : phase.status === 'done' ? 'text-[color:var(--text-secondary)]' : 'text-[color:var(--text-muted)]'}`}>
                        {phase.label}
                      </p>
                      {phase.error && (
                        <p className="text-xs text-red-400 mt-0.5">{phase.error}</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              {configError && !configuring && (
                <>
                  <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3 text-sm text-red-400">
                    {configError}
                  </div>
                  <div className="flex gap-3">
                    <button onClick={() => { setStep(1); setPhases(defaultPhases.map((p) => ({ ...p }))) }} className="flex-1 px-4 py-2 bg-white/5 text-[color:var(--text-secondary)] rounded-lg text-sm font-medium hover:bg-white/10 transition-colors">
                      Back
                    </button>
                  </div>
                </>
              )}
            </div>
          )}

          {/* Step 3: Done */}
          {step === 3 && (
            <div className="space-y-4">
              <div className="text-center py-4">
                <div className="w-14 h-14 rounded-2xl bg-[color:var(--evo-green)]/10 flex items-center justify-center mx-auto mb-3">
                  <CheckCircle size={28} className="text-[color:var(--evo-green)]" />
                </div>
                <p className="text-[color:var(--text-primary)] font-semibold mb-1">Connection ready!</p>
                <p className="text-[color:var(--text-muted)] text-sm">
                  Schema migrated. You can now create spaces and upload documents.
                </p>
              </div>
              <div className="flex gap-3">
                <button
                  onClick={() => onCreated()}
                  className="flex-1 px-4 py-2 bg-[color:var(--evo-green)] text-[color:var(--bg-primary)] rounded-lg text-sm font-semibold hover:bg-[color:var(--evo-green)]/90 transition-colors"
                >
                  Done
                </button>
              </div>
              {createdId && (
                <p className="text-center text-xs text-[color:var(--text-muted)]">
                  Connection ID: <span className="font-mono">{createdId}</span>
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
