import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Settings as SettingsIcon, Save } from 'lucide-react'
import { api } from '../lib/api'
import PageTabBar from '../components/PageTabBar'
import UsersPage from './Users'
import RolesPage from './Roles'
import AuditPage from './Audit'
import BackupsPage from './Backups'
import DocsPage from './Docs'

// ── Input / label class strings (same as Providers.tsx) ────────────────────
const inp = 'w-full px-4 py-3 rounded-lg bg-[#0f1520] border border-[#1e2a3a] text-[#e2e8f0] placeholder-[#3d4f65] text-sm transition-colors duration-200 focus:outline-none focus:border-[#00FFA7]/60 focus:ring-1 focus:ring-[#00FFA7]/20'
const lbl = 'block text-[11px] font-semibold text-[#98A2B3] mb-1.5 tracking-[0.08em] uppercase'

// ── Toast notification ──────────────────────────────────────────────────────
type ToastType = 'success' | 'error' | 'info'
interface Toast { id: number; type: ToastType; message: string }

function useToast() {
  const [toasts, setToasts] = useState<Toast[]>([])
  let counter = 0

  const show = useCallback((message: string, type: ToastType = 'success') => {
    const id = ++counter
    setToasts((prev) => [...prev, { id, type, message }])
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 3500)
  }, [])

  return { toasts, show }
}

function ToastStack({ toasts }: { toasts: Toast[] }) {
  if (!toasts.length) return null
  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium shadow-lg border transition-all ${
            t.type === 'success'
              ? 'bg-[#0b1018] border-[#00FFA7]/30 text-[#00FFA7]'
              : t.type === 'error'
              ? 'bg-[#0b1018] border-red-500/30 text-red-400'
              : 'bg-[#0b1018] border-[#21262d] text-[#98A2B3]'
          }`}
        >
          <span>{t.message}</span>
        </div>
      ))}
    </div>
  )
}

// ── Types ───────────────────────────────────────────────────────────────────
interface WorkspaceConfig {
  name: string
  owner: string
  company: string
  language: string
  timezone: string
  port: number
}

// ── Tab: Workspace ──────────────────────────────────────────────────────────
const TIMEZONES = [
  'America/Sao_Paulo', 'America/New_York', 'America/Chicago', 'America/Denver',
  'America/Los_Angeles', 'America/Toronto', 'America/Bogota', 'America/Lima',
  'America/Buenos_Aires', 'America/Santiago', 'America/Caracas', 'America/Manaus',
  'Europe/London', 'Europe/Paris', 'Europe/Berlin', 'Europe/Madrid', 'Europe/Rome',
  'Europe/Lisbon', 'Europe/Amsterdam', 'Europe/Stockholm', 'Europe/Warsaw',
  'Asia/Tokyo', 'Asia/Shanghai', 'Asia/Kolkata', 'Asia/Dubai', 'Asia/Singapore',
  'Asia/Seoul', 'Asia/Jakarta', 'Australia/Sydney', 'Pacific/Auckland',
  'UTC',
]

function WorkspaceTab({ showToast }: { showToast: (msg: string, type?: ToastType) => void }) {
  const { t } = useTranslation()
  const [config, setConfig] = useState<WorkspaceConfig>({
    name: '', owner: '', company: '', language: 'pt-BR', timezone: 'America/Sao_Paulo', port: 8080,
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.get('/settings/workspace')
      .then((data: any) => {
        const ws = data?.workspace || {}
        const db = data?.dashboard || {}
        setConfig({
          name: ws.name || '',
          owner: ws.owner || '',
          company: ws.company || '',
          language: ws.language || 'pt-BR',
          timezone: ws.timezone || 'America/Sao_Paulo',
          port: db.port || ws.port || 8080,
        })
      })
      .catch(() => showToast('Failed to load workspace config', 'error'))
      .finally(() => setLoading(false))
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      await api.put('/settings/workspace', {
        workspace: {
          name: config.name,
          owner: config.owner,
          company: config.company,
          language: config.language,
          timezone: config.timezone,
        },
        dashboard: { port: config.port },
      })
      showToast('Workspace saved successfully')
    } catch {
      showToast('Failed to save workspace config', 'error')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return (
    <div className="space-y-4">
      {[...Array(6)].map((_, i) => <div key={i} className="skeleton h-14 rounded-lg" />)}
    </div>
  )

  return (
    <div className="max-w-xl space-y-5">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className={lbl}>{t('settings.name')}</label>
          <input
            type="text"
            className={inp}
            value={config.name}
            onChange={(e) => setConfig((p) => ({ ...p, name: e.target.value }))}
            placeholder={t('settings.workspacePlaceholder')}
          />
        </div>
        <div>
          <label className={lbl}>{t('settings.owner')}</label>
          <input
            type="text"
            className={inp}
            value={config.owner}
            onChange={(e) => setConfig((p) => ({ ...p, owner: e.target.value }))}
            placeholder={t('settings.ownerPlaceholder')}
          />
        </div>
        <div>
          <label className={lbl}>{t('settings.company')}</label>
          <input
            type="text"
            className={inp}
            value={config.company}
            onChange={(e) => setConfig((p) => ({ ...p, company: e.target.value }))}
            placeholder={t('settings.companyPlaceholder')}
          />
        </div>
        <div>
          <label className={lbl}>{t('settings.language')}</label>
          <select
            className={inp}
            value={config.language}
            onChange={(e) => setConfig((p) => ({ ...p, language: e.target.value }))}
          >
            <option value="pt-BR">pt-BR — Português (Brasil)</option>
            <option value="pt-PT">pt-PT — Português (Portugal)</option>
            <option value="en-US">en-US — English (US)</option>
            <option value="en-GB">en-GB — English (UK)</option>
            <option value="es">es — Español</option>
            <option value="es-MX">es-MX — Español (México)</option>
            <option value="fr">fr — Français</option>
            <option value="de">de — Deutsch</option>
            <option value="it">it — Italiano</option>
            <option value="ja">ja — 日本語</option>
            <option value="ko">ko — 한국어</option>
            <option value="zh-CN">zh-CN — 中文 (简体)</option>
            <option value="zh-TW">zh-TW — 中文 (繁體)</option>
            <option value="ru">ru — Русский</option>
            <option value="ar">ar — العربية</option>
            <option value="hi">hi — हिन्दी</option>
            <option value="nl">nl — Nederlands</option>
            <option value="pl">pl — Polski</option>
            <option value="tr">tr — Türkçe</option>
            <option value="uk">uk — Українська</option>
          </select>
        </div>
        <div>
          <label className={lbl}>{t('settings.timezone')}</label>
          <select
            className={inp}
            value={config.timezone}
            onChange={(e) => setConfig((p) => ({ ...p, timezone: e.target.value }))}
          >
            {TIMEZONES.map((tz) => (
              <option key={tz} value={tz}>{tz}</option>
            ))}
          </select>
        </div>
        <div>
          <label className={lbl}>{t('settings.port')}</label>
          <input
            type="number"
            className={inp}
            value={config.port}
            onChange={(e) => setConfig((p) => ({ ...p, port: parseInt(e.target.value) || 8080 }))}
            min={1024}
            max={65535}
          />
        </div>
      </div>

      <div className="pt-2">
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-[#00FFA7] text-[#080c14] font-semibold text-sm hover:bg-[#00e69a] transition-colors disabled:opacity-40"
        >
          <Save size={14} />
          {saving ? t('common.saving') : t('settings.saveWorkspace')}
        </button>
      </div>
    </div>
  )
}

// ── Tab: Backups ───────────────────────────────────────────────────────────
// Substituiu a aba Rotinas (agora tem rota própria em Agentes → Rotinas e é o
// lugar canônico p/ agendar). Backups veio para cá porque era uma página só de
// "Configurações" sem casa no menu principal — e gestão de pessoas ganhou as
// três abas seguintes em vez de ocupar essa aqui.
function BackupsTab() { return <BackupsPage /> }

// ── Tabs: Users / Roles / Audit ─────────────────────────────────────────────
// A página de Configurações não é mais onde moram as listas de gestão de
// pessoas — mas também não pode sumir para quem não tem a permissão 'users'
// na sidebar. Aqui reutilizamos as mesmas páginas (sem duplicar header, o
// título geral já é "Configurações") em três abas dedicadas.

function UsersTab() { return <UsersPage /> }
function RolesTab() { return <RolesPage /> }
function AuditTab() { return <AuditPage /> }
// Docs embutido: layout interno próprio (sidebar de nav + artigo), precisa de
// altura definida pra funcionar no lugar do scroll da página.
function DocsTab() {
  return (
    <div className="h-[calc(100vh-260px)] min-h-[420px] -mx-2">
      <DocsPage embedded />
    </div>
  )
}

// ── Main Settings page ──────────────────────────────────────────────────────
const TABS = [
  { key: 'workspace', labelKey: 'settings.tabs.workspace' },
  { key: 'backups', labelKey: 'settings.tabs.backups' },
  { key: 'docs', labelKey: 'settings.tabs.docs' },
  { key: 'users', labelKey: 'settings.tabs.users' },
  { key: 'roles', labelKey: 'settings.tabs.roles' },
  { key: 'audit', labelKey: 'settings.tabs.audit' },
] as const

type TabKey = 'workspace' | 'backups' | 'docs' | 'users' | 'roles' | 'audit'

export default function Settings() {
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState<TabKey>('workspace')
  const { toasts, show: showToast } = useToast()

  return (
    <div className={`${activeTab === 'docs' ? '' : 'max-w-[1200px] mx-auto'} font-[Inter,-apple-system,sans-serif] ${activeTab === 'docs' ? 'h-full min-h-0' : ''}`}>
      {/* Header */}
      <div className="flex items-center gap-3 mb-8">
        <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-[#161b22] border border-[#21262d]">
          <SettingsIcon size={20} className="text-[#00FFA7]" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight">{t('settings.title')}</h1>
          <p className="text-[#98A2B3] text-sm mt-0.5">{t('settings.headerSubtitle')}</p>
        </div>
      </div>

      {/* Tabs */}
      <PageTabBar<TabKey> ariaLabel={t('settings.title')} extraClass="mb-7" active={activeTab} onSelect={setActiveTab} tabs={TABS.map((x) => ({ key: x.key, label: t(x.labelKey) }))} />

      {/* Tab content */}
      {activeTab === 'workspace' && <WorkspaceTab showToast={showToast} />}
      {activeTab === 'backups' && <BackupsTab />}
      {activeTab === 'docs' && <DocsTab />}
      {activeTab === 'users' && <UsersTab />}
      {activeTab === 'roles' && <RolesTab />}
      {activeTab === 'audit' && <AuditTab />}

      <ToastStack toasts={toasts} />
    </div>
  )
}
