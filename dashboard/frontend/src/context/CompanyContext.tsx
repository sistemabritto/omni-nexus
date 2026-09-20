import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { api } from '../lib/api'

// W3 (2026-09-20): empresa ativa é sessão local (sem coluna em users em v1).
// Persiste em localStorage; as listagens recebem ?company_id= via companyParam().
const STORAGE_KEY = 'evo:active_company'

export interface Company {
  id: number
  name: string
  slug: string
  logo_url?: string | null
}

interface CompanyContextValue {
  companies: Company[]
  activeCompanyId: number | null
  activeCompany: Company | null
  setActiveCompanyId: (id: number | null) => void
  reload: () => Promise<void>
}

const CompanyContext = createContext<CompanyContextValue>({
  companies: [],
  activeCompanyId: null,
  activeCompany: null,
  setActiveCompanyId: () => {},
  reload: async () => {},
})

export function CompanyProvider({ children }: { children: ReactNode }) {
  const [companies, setCompanies] = useState<Company[]>([])
  const [activeCompanyId, setActiveState] = useState<number | null>(() => {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw !== null && raw !== '') {
      const parsed = Number(raw)
      if (Number.isFinite(parsed)) return parsed
    }
    return null
  })

  const reload = useCallback(async () => {
    try {
      const res = await api.get('/companies')
      if (Array.isArray(res)) setCompanies(res)
    } catch {
      // 403 (sem goals:view) ou rede — mantém lista vazia
    }
  }, [])

  useEffect(() => {
    reload()
  }, [reload])

  const setActiveCompanyId = useCallback((id: number | null) => {
    setActiveState(id)
    if (id === null) localStorage.removeItem(STORAGE_KEY)
    else localStorage.setItem(STORAGE_KEY, String(id))
  }, [])

  const value = useMemo<CompanyContextValue>(() => {
    const activeCompany =
      companies.find((c) => c.id === activeCompanyId) ?? null
    return {
      companies,
      activeCompanyId,
      activeCompany,
      setActiveCompanyId,
      reload,
    }
  }, [companies, activeCompanyId, setActiveCompanyId, reload])

  return (
    <CompanyContext.Provider value={value}>{children}</CompanyContext.Provider>
  )
}

export function useCompanies() {
  return useContext(CompanyContext)
}
