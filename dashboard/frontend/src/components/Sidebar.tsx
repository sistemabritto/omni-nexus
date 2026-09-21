import { useState, useEffect, useCallback, useRef } from 'react'
import { NavLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../context/AuthContext'
import { useCompanies, type Company } from '../context/CompanyContext'
import CompanyManagerModal from './CompanyManagerModal'
import NotificationBell from './NotificationBell'
import {
  LayoutDashboard, Bot, Clock,
  LogOut, Menu, X,
  ArrowUpCircle, ChevronDown, Webhook, Heart, Target,
  Puzzle, Columns3,
  Plug, FolderOpen, Settings, Building2, Settings2, Check, Plus,
} from 'lucide-react'
import {
  getAllPluginSidebarGroups,
  getAllPluginPages,
  type PluginSidebarGroup,
  type PluginPage,
} from '../lib/plugin-ui-registry'

interface VersionInfo {
  current: string
  latest: string | null
  update_available: boolean
  release_url: string | null
  release_notes: string | null
}

interface NavItem {
  to: string
  labelKey: string           // i18n key under nav.*
  icon: React.ComponentType<{ size?: number }>
  resource: string | null
  desktopOnly?: boolean
}

// Seção fixa: título discreto (uppercase) SEM chevron e SEM colapso. O estado
// de colapsar ficou só nos grupos de plugins injetados. Configurações não é
// mais seção de menu — virou a engrenagem ao lado do nome do usuário no rodapé.
interface NavSection {
  key: string                // i18n key under nav.groups.*
  title?: string             // undefined = links soltos sem título
  adminOnly?: boolean
  items: NavItem[]
}

const navSections: NavSection[] = [
  {
    key: 'cockpit',
    title: 'Cockpit',
    items: [
      // Os 5 domínios viraram abas da única página /?tab=. 1 link no topo.
      { to: '/', labelKey: 'overview', icon: LayoutDashboard, resource: null },
    ],
  },
   {
    // Missões → Projetos → Metas → Tickets numa única árvore (W2, 2026-09-20 —
    // a unificação dos zôms /projects e /goals). Ficam sem título, entre
    // Cockpit e a seção Inteligência. Materiais vai no fim do bloco — abaixo do
    // Kanban, logo acima do título Inteligência (decisão do dono, 20/09): é
    // material de trabalho, não "cérebro".
    key: 'projetos',
    items: [
      { to: '/missions', labelKey: 'missions', icon: Target, resource: 'goals' },
      { to: '/kanban', labelKey: 'kanban', icon: Columns3, resource: 'tickets' },
      { to: '/workspace', labelKey: 'workspace', icon: FolderOpen, resource: 'workspace' },
    ],
  },
  {
    key: 'inteligencia',
    title: 'Inteligência',
    items: [
      // Tudo que dá cérebro à operação: agentes + o que acorda cada um +
      // o hub de integrações (APIs).
      { to: '/agents', labelKey: 'agents', icon: Bot, resource: 'agents' },
      { to: '/heartbeats', labelKey: 'heartbeats', icon: Heart, resource: 'heartbeats' },
      { to: '/routines', labelKey: 'routines', icon: Clock, resource: 'routines' },
      { to: '/triggers', labelKey: 'triggers', icon: Webhook, resource: 'triggers' },
      { to: '/inteligencia', labelKey: 'integrations', icon: Plug, resource: null },
    ],
  },
]

const STORAGE_KEY = 'sidebar-collapsed-groups'

function loadCollapsedState(): Record<string, boolean> {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) return JSON.parse(stored)
  } catch {}
  return {}
}

function saveCollapsedState(state: Record<string, boolean>) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch {}
}

const roleBadgeClass: Record<string, string> = {
  admin: 'bg-purple-500/20 text-purple-400',
  operator: 'bg-blue-500/20 text-blue-400',
  viewer: 'bg-gray-500/20 text-gray-400',
}

// W3 (2026-09-20): switcher de empresa — popover no rodapé, junto ao perfil.
// Substitui o <select> nativo (que abria a lista do browser, tosco e sem logo).
// Menu abre pra cima, fecha com Esc/clique fora; check no item ativo.
function CompanySwitcher({
  companies,
  activeCompanyId,
  onSelect,
  onManage,
  onCreate,
  t,
}: {
  companies: Company[]
  activeCompanyId: number | null
  onSelect: (id: number | null) => void
  onManage: (id: number) => void
  onCreate: () => void
  t: (key: string) => string
}) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function onDown(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false)
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const active = companies.find((c) => c.id === activeCompanyId) ?? null

  const mark = (company: Company | null, size = 14) =>
    company?.logo_url ? (
      <img src={company.logo_url} alt="" className="rounded-md object-cover shrink-0" style={{ width: size, height: size }} />
    ) : (
      <span className="flex items-center justify-center rounded-md bg-white/5 text-[#98A2B3] shrink-0" style={{ width: size, height: size }}>
        <Building2 size={size * 0.9} />
      </span>
    )

  // Renderizado DENTRO do card do perfil (linha 2 da conta). O wrapper do
  // card é o posicionamento (relative): o menu abre pra cima na largura do
  // card, sem estourar a sidebar. Fecha com Esc/clique fora.
  return (
    <div ref={rootRef}>
      <button
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        title={t('nav.companies.activeLabel')}
        className={`flex items-center gap-1.5 min-w-0 text-left bg-transparent border p-0 cursor-pointer group rounded-md focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#00FFA7]/60 ${
          open ? 'text-[#D0D5DD]' : ''
        }`}
      >
        {mark(active)}
        <span className="text-xs truncate group-hover:text-[#D0D5DD] text-[#98A2B3] transition-colors">
          {active ? active.name : t('nav.companies.all')}
        </span>
        <ChevronDown
          size={12}
          className={`text-[#475467] transition-transform duration-200 shrink-0 ${open ? 'rotate-180' : 'group-hover:text-[#98A2B3]'}`}
        />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute bottom-full -left-3 right-0 mb-1.5 z-50 rounded-xl border border-white/10 bg-[#0C111D]/95 backdrop-blur-md shadow-2xl shadow-black/60 p-1"
        >
          <div className="px-2.5 pt-1.5 pb-1 text-[10px] uppercase tracking-wider text-[#475467] font-semibold select-none">
            {t('nav.companies.activeLabel')}
          </div>

          <button
            role="menuitemradio"
            aria-checked={activeCompanyId === null}
            onClick={() => { onSelect(null); setOpen(false) }}
            className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-left text-sm transition-colors ${
              activeCompanyId === null
                ? 'text-white bg-[#00FFA7]/10'
                : 'text-[#98A2B3] hover:text-[#D0D5DD] hover:bg-white/5'
            }`}
          >
            <Building2 size={15} className="shrink-0 opacity-70" />
            <span className="flex-1 truncate font-medium">{t('nav.companies.all')}</span>
            {activeCompanyId === null && <Check size={14} className="text-[#00FFA7] shrink-0" />}
          </button>

          <div className="my-1 h-px bg-white/10" />

          {companies.map((c) => (
            <button
              key={c.id}
              role="menuitemradio"
              aria-checked={c.id === activeCompanyId}
              onClick={() => { onSelect(c.id); setOpen(false) }}
              className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-left text-sm transition-colors ${
                c.id === activeCompanyId
                  ? 'text-white bg-[#00FFA7]/10'
                  : 'text-[#98A2B3] hover:text-[#D0D5DD] hover:bg-white/5'
              }`}
            >
              {mark(c, 22)}
              <span className="flex-1 min-w-0">
                <span className="block truncate font-medium">{c.name}</span>
                <span className="block text-[10px] opacity-70 truncate">{c.slug}</span>
              </span>
              {c.id === activeCompanyId && <Check size={14} className="text-[#00FFA7] shrink-0" />}
            </button>
          ))}

          <div className="my-1 h-px bg-white/10" />

          <button
            role="menuitem"
            onClick={() => { onManage(activeCompanyId ?? companies[0]?.id ?? 0); setOpen(false) }}
            className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-left text-xs text-[#98A2B3] hover:text-[#D0D5DD] hover:bg-white/5 transition-colors"
          >
            <Settings2 size={14} className="shrink-0 opacity-70" />
            {t('nav.companies.manage')}
          </button>

          <button
            role="menuitem"
            onClick={() => { onCreate(); setOpen(false) }}
            className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-left text-xs font-medium text-[#00FFA7] hover:bg-[#00FFA7]/10 transition-colors mt-0.5"
          >
            <Plus size={14} className="shrink-0" />
            {t('nav.companies.newTitle')}
          </button>
        </div>
      )}
    </div>
  )
}



export default function Sidebar() {
  const { user, logout, hasPermission } = useAuth()
  const { companies, activeCompanyId, activeCompany, setActiveCompanyId } = useCompanies()
  const [manageCompany, setManageCompany] = useState<number | 'new' | null>(null)
  const { t } = useTranslation()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [versionInfo, setVersionInfo] = useState<VersionInfo | null>(null)
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>(loadCollapsedState)
  // Wave 2.1: plugin sidebar groups — refreshed after registry hydration
  const [pluginGroups, setPluginGroups] = useState<(PluginSidebarGroup & { slug: string })[]>([])
  const [pluginPages, setPluginPages] = useState<(PluginPage & { slug: string; bundle_url: string })[]>([])

  useEffect(() => {
    fetch('/api/version/check')
      .then((r) => r.json())
      .then((data) => setVersionInfo(data))
      .catch(() => {})
  }, [])

  // Refresh plugin sidebar groups after registry hydration (hydration is async, runs post-login)
  useEffect(() => {
    function refresh() {
      setPluginGroups(getAllPluginSidebarGroups())
      setPluginPages(getAllPluginPages())
    }
    // Initial read (may be empty before hydration completes)
    refresh()
    // Re-read after a short delay to catch async hydration completing
    const t1 = setTimeout(refresh, 500)
    const t2 = setTimeout(refresh, 2000)
    return () => { clearTimeout(t1); clearTimeout(t2) }
  }, [])

  const toggleGroup = useCallback((key: string) => {
    setCollapsed((prev) => {
      const next = { ...prev, [key]: !prev[key] }
      saveCollapsedState(next)
      return next
    })
  }, [])

  const renderLink = (item: NavItem) => (
    <NavLink
      key={item.to}
      to={item.to}
      end={item.to === '/'}
      onClick={() => setMobileOpen(false)}
      className={({ isActive }) =>
        `items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#00FFA7]/60 ${
          item.desktopOnly ? 'hidden lg:flex' : 'flex'
        } ${
          isActive
            ? 'text-[#00FFA7] bg-[#00FFA7]/10 border-l-2 border-[#00FFA7]'
            : 'text-[#98A2B3] hover:text-[#D0D5DD] hover:bg-white/5 border-l-2 border-transparent'
        }`
      }
    >
      <item.icon size={16} />
      {t(`nav.${item.labelKey}`)}
    </NavLink>
  )

  const renderSection = (section: NavSection) => {
    const visibleItems = section.items.filter(
      (item) => item.resource === null || hasPermission(item.resource, 'view')
    )
    if (visibleItems.length === 0) return null

    return (
      <div key={section.key} className="mb-1">
        {section.title && (
          <div className="px-3 pt-3 pb-1">
            <span className="text-[10px] uppercase tracking-wider text-[#475467] font-semibold">
              {t(`nav.groups.${section.key}`)}
            </span>
          </div>
        )}
        <div className={`flex flex-col gap-0.5 ${section.title ? 'mt-0' : 'mt-2 first:mt-0'}`}>
          {visibleItems.map(renderLink)}
        </div>
      </div>
    )
  }

  const sidebarContent = (
    <>
      <div className="px-5 py-6 flex items-center justify-between">
        <img
          src={activeCompany?.logo_url ?? '/EVO_NEXUS.webp'}
          alt={activeCompany?.name ?? 'EvoNexus'}
          className="h-8 w-auto"
        />
        <div className="flex items-center gap-1">
          <NotificationBell />
          <button onClick={() => setMobileOpen(false)} className="lg:hidden p-1 rounded hover:bg-white/10 text-[#98A2B3]">
            <X size={20} />
          </button>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 pb-4">
        {navSections.map(renderSection)}

        {/* Wave 2.1: Plugin sidebar groups injected after native groups */}
        {pluginGroups.map((group) => {
          const groupPages = pluginPages.filter(
            (p) => p.slug === group.slug && p.sidebar_group === group.id
          )
          if (groupPages.length === 0) return null
          const isCollapsed = collapsed[`plugin-${group.slug}-${group.id}`] ?? false
          const storageKey = `plugin-${group.slug}-${group.id}`
          return (
            <div key={storageKey} className="mb-1">
              {group.collapsible !== false ? (
                <button
                  onClick={() => toggleGroup(storageKey)}
                  className="w-full flex items-center justify-between px-3 py-1.5 mt-2 group cursor-pointer"
                >
                  <span className="text-[10px] uppercase tracking-wider text-[#98A2B3] font-semibold select-none">
                    {group.label}
                  </span>
                  <ChevronDown
                    size={12}
                    className={`text-[#98A2B3] transition-transform duration-200 group-hover:text-[#D0D5DD] ${
                      isCollapsed ? '-rotate-90' : ''
                    }`}
                  />
                </button>
              ) : (
                <div className="px-3 py-1.5">
                  <span className="text-[10px] uppercase tracking-wider text-[#98A2B3] font-semibold">
                    {group.label}
                  </span>
                </div>
              )}
              <div
                className={`overflow-hidden transition-all duration-200 ease-in-out ${
                  group.collapsible !== false && isCollapsed ? 'max-h-0 opacity-0' : 'max-h-[720px] opacity-100'
                }`}
              >
                <div className="flex flex-col gap-0.5">
                  {[...groupPages]
                    .sort((a, b) => (a.order ?? 999) - (b.order ?? 999))
                    .map((page) => (
                      <NavLink
                        key={`${page.slug}-${page.id}`}
                        to={`/plugins-ui/${page.slug}/${page.path}`}
                        onClick={() => setMobileOpen(false)}
                        className={({ isActive }) =>
                          `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors border-l-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#00FFA7]/60 ${
                            isActive
                              ? 'text-[#00FFA7] bg-[#00FFA7]/10 border-[#00FFA7]'
                              : 'text-[#98A2B3] hover:text-[#D0D5DD] hover:bg-white/5 border-transparent'
                          }`
                        }
                      >
                        <Puzzle size={16} />
                        {page.label}
                      </NavLink>
                    ))}
                </div>
              </div>
            </div>
          )
        })}
      </nav>

      {user && (
        <div className="px-3 py-3 border-t border-[#344054] space-y-2">
          {/* W3 (2026-09-21): empresa INTEGRADA ao card do perfil — linha 2 do
              perfil (logo + nome da empresa ativa), não uma linha solta acima.
              Clicar abre o seletor; badge de role fica na linha 1, ao lado do nome. */}
          <div className="relative">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-[#00FFA7]/20 text-[#00FFA7] flex items-center justify-center text-sm font-bold shrink-0">
                {(user.display_name || user.username).charAt(0).toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5 min-w-0">
                  <p className="text-sm text-white font-medium truncate">{user.display_name || user.username}</p>
                  <span className={`shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium ${roleBadgeClass[user.role] || roleBadgeClass.viewer}`}>
                    {user.role}
                  </span>
                </div>
                {companies.length > 0 ? (
                  <CompanySwitcher
                    companies={companies}
                    activeCompanyId={activeCompanyId}
                    onSelect={setActiveCompanyId}
                    onManage={(id) => setManageCompany(id || companies[0]?.id || null)}
                    onCreate={() => setManageCompany('new')}
                    t={t}
                  />
                ) : (
                  <span className="sr-only">{t('nav.companies.all')}</span>
                )}
              </div>
              <NavLink
                to="/settings"
                onClick={() => setMobileOpen(false)}
                className={({ isActive }) =>
                  `p-2 rounded-xl transition-colors shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#00FFA7]/60 ${
                    isActive
                      ? 'bg-[#00FFA7]/15 text-[#00FFA7]'
                      : 'bg-white/5 text-[#98A2B3] hover:bg-white/10 hover:text-[#D0D5DD]'
                  }`
                }
                title={t('nav.settings')}
              >
                <Settings size={20} />
              </NavLink>
              <button
                onClick={logout}
                className="p-1.5 rounded-lg text-[#98A2B3] hover:text-red-400 hover:bg-red-500/10 transition-colors shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400/60"
                title={t('nav.logout')}
              >
                <LogOut size={16} />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Version indicator */}
      {versionInfo && (
        <div className="px-4 py-2 border-t border-[#344054]/50">
          <div className="flex items-center justify-between text-[11px]">
            <span className="text-[#98A2B3]">v{versionInfo.current}</span>
            {versionInfo.update_available && versionInfo.release_url && (
              <a
                href={versionInfo.release_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 text-[#00FFA7] hover:text-[#00FFA7]/80 transition-colors"
                title={t('nav.updateAvailable', { version: versionInfo.latest })}
              >
                <ArrowUpCircle size={12} />
                <span>v{versionInfo.latest}</span>
              </a>
            )}
          </div>
        </div>
      )}

      {/* Credits */}
      <div className="px-4 py-3 border-t border-[#344054]/50">
        <a
          href="https://evolutionfoundation.com.br"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-center gap-1.5 text-[10px] text-[#98A2B3] hover:text-[#00FFA7] transition-colors"
        >
          by <span className="font-semibold text-[#00FFA7]/60">Evolution Foundation</span>
        </a>
      </div>

      {manageCompany !== null && (
        <CompanyManagerModal
          company={manageCompany === 'new' ? null : companies.find((c) => c.id === manageCompany) ?? null}
          onClose={() => setManageCompany(null)}
        />
      )}
    </>
  )

  return (
    <>
      {/* Mobile hamburger */}
      <button
        onClick={() => setMobileOpen(true)}
        className="fixed top-4 left-4 z-50 lg:hidden p-2 rounded-lg bg-[#182230] border border-[#344054] text-[#D0D5DD] hover:text-[#00FFA7] transition-colors"
      >
        <Menu size={20} />
      </button>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div className="fixed inset-0 bg-black/60 z-40 lg:hidden" onClick={() => setMobileOpen(false)} />
      )}

      {/* Sidebar */}
      <aside className={`
        fixed left-0 top-0 bottom-0 w-60 bg-[#0a0f1a] border-r border-[#344054] flex flex-col z-50
        transition-transform duration-200 ease-in-out
        lg:translate-x-0
        ${mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
      `}>
        {sidebarContent}
      </aside>
    </>
  )
}
