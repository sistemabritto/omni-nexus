// Modified 2026-10-15: OmniNexus Live global UI system; original EvoNexus attribution retained.
import { NavLink, Outlet } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Database } from 'lucide-react'
import { useAuth } from '../../context/AuthContext'
import { KnowledgeProvider } from '../../context/KnowledgeContext'
import HubBackLink from '../../components/HubBackLink'

type Tab = { to: string; labelKey: string; exact?: boolean }

const tabs: Tab[] = [
  { to: '/knowledge', labelKey: 'knowledge.connections', exact: true },
  { to: '/knowledge/settings', labelKey: 'knowledge.settings' },
]

export default function KnowledgeLayout() {
  const { t } = useTranslation()
  const { hasPermission } = useAuth()

  if (!hasPermission('knowledge', 'view')) {
    return (
      <div className="flex items-center justify-center h-64 text-[color:var(--text-muted)] text-sm">
        {t('knowledge.noPermission')}
      </div>
    )
  }

  return (
    <KnowledgeProvider>
      <div>
        <HubBackLink />
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-[color:var(--text-primary)] flex items-center gap-2">
            <Database size={22} className="text-[color:var(--evo-green)]" />
            {t('knowledge.title')}
          </h1>
          <p className="text-[color:var(--text-muted)] mt-1 text-sm">
            {t('knowledge.layoutSubtitle')}
          </p>
        </div>

        {/* Global tabs (connection-agnostic) */}
        <div className="flex gap-1 mb-6 border-b border-[color:var(--border)] overflow-x-auto">
          {tabs.map((tab) => (
            <NavLink
              key={tab.to}
              to={tab.to}
              end={tab.exact}
              className={({ isActive }) =>
                `px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px whitespace-nowrap ${
                  isActive
                    ? 'text-[color:var(--evo-green)] border-[color:var(--evo-green)]'
                    : 'text-[color:var(--text-muted)] border-transparent hover:text-[color:var(--text-secondary)]'
                }`
              }
            >
              {t(tab.labelKey)}
            </NavLink>
          ))}
        </div>

        {/* Page content */}
        <Outlet />
      </div>
    </KnowledgeProvider>
  )
}
