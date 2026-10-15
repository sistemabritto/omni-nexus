import { useLayoutEffect } from 'react'
import { useCompanies } from '../context/CompanyContext'
import { managedSession } from './managed-session'

// Remains mounted across routes: a global company change never rebinds a live call.
export default function LiveCompanyBinding() {
  const { activeCompanyId } = useCompanies()
  useLayoutEffect(() => {
    managedSession.syncCompany(activeCompanyId)
  }, [activeCompanyId])
  return null
}
