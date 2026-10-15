// Modified 2026-10-15: OmniNexus Live global UI system; original EvoNexus attribution retained.
import { useEffect, useState } from 'react'
import { Video, CheckCircle2, AlertCircle, Loader2, Eye, EyeOff, RefreshCw } from 'lucide-react'
import { api } from '../lib/api'

// Admin-only config panel for the Postiz publish bridge core integration
// (social-media-production, briefing Etapa 13/14). Deliberately a small,
// self-contained component instead of touching the generic 2000+ line
// Integrations.tsx custom-integration machinery — Postiz has its own
// dedicated, masked-secret admin endpoint
// (routes/integrations_core_postiz.py), not the generic env-var CRUD used
// by custom/plugin integrations.

const FIELDS: { key: string; label: string; secret?: boolean; placeholder?: string }[] = [
  { key: 'POSTIZ_URL', label: 'Postiz URL', placeholder: 'https://post.workflowapi.com.br' },
  { key: 'POSTIZ_API_KEY', label: 'API Key', secret: true, placeholder: '****' },
  { key: 'POSTIZ_INTEGRATION_INSTAGRAM_ID', label: 'Integration ID — Instagram' },
  { key: 'POSTIZ_INTEGRATION_YOUTUBE_ID', label: 'Integration ID — YouTube' },
  { key: 'POSTIZ_INTEGRATION_LINKEDIN_ID', label: 'Integration ID — LinkedIn' },
  { key: 'POSTIZ_INTEGRATION_TIKTOK_ID', label: 'Integration ID — TikTok' },
  { key: 'POSTIZ_REQUEST_TIMEOUT_SECONDS', label: 'Timeout de requisição (s)', placeholder: '120' },
  { key: 'POSTIZ_UPLOAD_TIMEOUT_SECONDS', label: 'Timeout de upload (s)', placeholder: '900' },
]

type TestResult = {
  ok: boolean
  detail?: string
  platforms?: Record<string, { connected: boolean; id: string | null }>
}

export default function PostizCoreConfigCard() {
  const [values, setValues] = useState<Record<string, string>>({})
  const [defaultMode, setDefaultMode] = useState<'draft' | 'schedule'>('draft')
  const [timezone, setTimezone] = useState('America/Bahia')
  const [configured, setConfigured] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<TestResult | null>(null)
  const [showSecret, setShowSecret] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saveNote, setSaveNote] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    setError(null)
    api.get('/integrations/core/postiz')
      .then((data) => {
        setValues(data?.config || {})
        setDefaultMode((data?.config?.SOCIAL_DEFAULT_POST_MODE as 'draft' | 'schedule') || 'draft')
        setTimezone(data?.config?.MEDIA_TIMEZONE || 'America/Bahia')
        setConfigured(!!data?.configured)
      })
      .catch((e) => setError(e?.message || 'Falha ao carregar configuração do Postiz'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    setSaveNote(null)
    try {
      const body = {
        ...values,
        SOCIAL_DEFAULT_POST_MODE: defaultMode,
        MEDIA_TIMEZONE: timezone,
      }
      const data = await api.put('/integrations/core/postiz', body)
      setValues(data?.config || {})
      setConfigured(!!data?.configured)
      setSaveNote(data?.note || 'Configuração salva.')
    } catch (e: any) {
      setError(e?.message || 'Falha ao salvar')
    } finally {
      setSaving(false)
    }
  }

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    setError(null)
    try {
      const data = await api.post('/integrations/core/postiz/test')
      setTestResult(data)
    } catch (e: any) {
      setTestResult({ ok: false, detail: e?.message || 'Falha ao testar conexão' })
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="mb-6">
      <div className="flex items-center gap-2.5 mb-3">
        <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-[color:var(--evo-green)]/8 border border-[color:var(--evo-green)]/15">
          <Video size={14} className="text-[color:var(--evo-green)]" />
        </div>
        <h2 className="text-base font-semibold text-[color:var(--text-primary)]">Postiz (produção de mídia social)</h2>
        <span
          className="text-xs px-2 py-0.5 rounded-full border"
          style={{
            color: configured ? '#00FFA7' : '#8b949e',
            borderColor: configured ? 'rgba(0,255,167,0.3)' : '#21262d',
            background: configured ? 'rgba(0,255,167,0.08)' : 'transparent',
          }}
        >
          {configured ? 'Conectado' : 'Não configurado'}
        </span>
      </div>

      <div className="rounded-xl border border-[color:var(--border)] bg-[color:var(--bg-card)] p-5">
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-[color:var(--text-muted)]">
            <Loader2 size={14} className="animate-spin" /> Carregando...
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
              {FIELDS.map((field) => (
                <div key={field.key}>
                  <label className="block text-xs text-[color:var(--text-muted)] mb-1">{field.label}</label>
                  <div className="relative">
                    <input
                      type={field.secret && !showSecret ? 'password' : 'text'}
                      value={values[field.key] ?? ''}
                      placeholder={field.placeholder}
                      onChange={(e) => setValues((v) => ({ ...v, [field.key]: e.target.value }))}
                      className="w-full bg-[color:var(--bg-primary)] border border-[color:var(--border)] rounded-lg px-3 py-2 text-sm text-[color:var(--text-primary)] focus:outline-none focus:border-[color:var(--evo-green)]/40"
                    />
                    {field.secret && (
                      <button
                        type="button"
                        onClick={() => setShowSecret((s) => !s)}
                        className="absolute right-2 top-1/2 -translate-y-1/2 text-[color:var(--text-muted)] hover:text-[color:var(--text-primary)]"
                      >
                        {showSecret ? <EyeOff size={14} /> : <Eye size={14} />}
                      </button>
                    )}
                  </div>
                </div>
              ))}

              <div>
                <label className="block text-xs text-[color:var(--text-muted)] mb-1">Modo de publicação padrão</label>
                <select
                  value={defaultMode}
                  onChange={(e) => setDefaultMode(e.target.value as 'draft' | 'schedule')}
                  className="w-full bg-[color:var(--bg-primary)] border border-[color:var(--border)] rounded-lg px-3 py-2 text-sm text-[color:var(--text-primary)] focus:outline-none focus:border-[color:var(--evo-green)]/40"
                >
                  <option value="draft">draft (nunca publica sozinho)</option>
                  <option value="schedule">schedule (agenda após aprovação)</option>
                </select>
              </div>
              <div>
                <label className="block text-xs text-[color:var(--text-muted)] mb-1">Timezone (entrada do usuário)</label>
                <input
                  type="text"
                  value={timezone}
                  onChange={(e) => setTimezone(e.target.value)}
                  placeholder="America/Bahia"
                  className="w-full bg-[color:var(--bg-primary)] border border-[color:var(--border)] rounded-lg px-3 py-2 text-sm text-[color:var(--text-primary)] focus:outline-none focus:border-[color:var(--evo-green)]/40"
                />
              </div>
            </div>

            {error && (
              <div className="flex items-center gap-2 text-xs text-[#f85149] mb-3">
                <AlertCircle size={13} /> {error}
              </div>
            )}
            {saveNote && !error && (
              <div className="text-xs text-[color:var(--text-muted)] mb-3">{saveNote}</div>
            )}
            {testResult && (
              <div className="mb-3 text-xs">
                <div className={`flex items-center gap-2 ${testResult.ok ? 'text-[color:var(--evo-green)]' : 'text-[#f85149]'}`}>
                  {testResult.ok ? <CheckCircle2 size={13} /> : <AlertCircle size={13} />}
                  {testResult.detail}
                </div>
                {testResult.platforms && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {Object.entries(testResult.platforms).map(([platform, info]) => (
                      <span
                        key={platform}
                        className="px-2 py-0.5 rounded-full border text-[11px]"
                        style={{
                          color: info.connected ? '#00FFA7' : '#8b949e',
                          borderColor: info.connected ? 'rgba(0,255,167,0.3)' : '#21262d',
                        }}
                      >
                        {platform}: {info.connected ? 'conectado' : 'não conectado'}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div className="flex items-center gap-2">
              <button
                onClick={handleSave}
                disabled={saving}
                className="px-3 py-1.5 rounded-lg text-sm font-medium bg-[color:var(--evo-green)]/10 border border-[color:var(--evo-green)]/30 text-[color:var(--evo-green)] hover:bg-[color:var(--evo-green)]/15 disabled:opacity-50"
              >
                {saving ? 'Salvando...' : 'Salvar'}
              </button>
              <button
                onClick={handleTest}
                disabled={testing || !configured}
                className="px-3 py-1.5 rounded-lg text-sm font-medium bg-[color:var(--bg-card)] border border-[color:var(--border)] text-[color:var(--text-primary)] hover:border-[color:var(--text-muted)]/40 disabled:opacity-50"
              >
                {testing ? 'Testando...' : 'Testar conexão'}
              </button>
              <button
                onClick={load}
                className="ml-auto p-1.5 rounded-lg text-[color:var(--text-muted)] hover:text-[color:var(--text-primary)] hover:bg-[color:var(--border)]"
                title="Recarregar"
              >
                <RefreshCw size={14} />
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
