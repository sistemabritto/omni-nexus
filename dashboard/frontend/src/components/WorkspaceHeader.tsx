// OmniNexus Live global frame. Company is UI context, not a tenancy security claim.
import { Building2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useLocation } from 'react-router-dom'
import { useCompanies } from '../context/CompanyContext'
import { getWorkspaceArea } from '../lib/workspace-routes'
export default function WorkspaceHeader() {
  const { t } = useTranslation()
  const { pathname } = useLocation()
  const { activeCompany } = useCompanies()
  const [prefix, fallback] = getWorkspaceArea(pathname)
  const key = prefix === '/' ? 'root' : prefix.slice(1).replaceAll('-', '_')
  const title = t(`shell.links.${key}`, {defaultValue:fallback})
  return <header className="omn-workspace-header"><div className="omn-area"><strong title={title}>{title}</strong><span>{t('shell.subtitle')}</span></div><div className="omn-company-context" title={t('shell.companyContext')}><Building2 size={16} aria-hidden="true" /><span>{activeCompany?.name || t('shell.noCompany')}</span></div></header>
}
