import { lazy, Suspense, useEffect, useState } from 'react'
import { useLocation, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../context/AuthContext'
import PageTabBar from '../components/PageTabBar'

// "Materiais" — arquivos do negócio numa página só (revamp 20/09): abas
// Arquivos (árvore + editor) · Mídias (produção de vídeo) · Shares (links
// públicos). Deep-link por ?mat=. Deep-link de arquivo continua /workspace/<path>
// (sem ?mat=), que cai na aba Arquivos e mantém o comportamento antigo.
// As rotas standalone /media e /shares seguem existindo p/ links diretos.

type MateriaisTab = 'arquivos' | 'midias' | 'shares' | 'templates'

const MATERIAIS_TABS: { key: MateriaisTab; labelKey: string; resource: string | null }[] = [
  { key: 'arquivos', labelKey: 'materiais.tabs.arquivos', resource: 'workspace' },
  { key: 'midias', labelKey: 'nav.media', resource: 'media_jobs' },
  { key: 'shares', labelKey: 'nav.shareLinks', resource: 'workspace' },
  { key: 'templates', labelKey: 'nav.templates', resource: 'templates' },
]

const WorkspacePage = lazy(() => import('./Workspace'))
const MediaPage = lazy(() => import('./Media'))
const ShareLinksPage = lazy(() => import('./ShareLinks'))
const TemplatesPage = lazy(() => import('./Templates'))

export default function Materiais() {
  const { t } = useTranslation()
  const location = useLocation()
  const { hasPermission } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()

  const matParam = searchParams.get('mat')
  const visibleTabs = MATERIAIS_TABS.filter((x) => x.resource === null || hasPermission(x.resource, 'view'))
  // Deep-link de arquivo (/workspace/finance/x.md, sem ?mat=) → aba Arquivos.
  const hasFileSegment = location.pathname.replace(/^\/workspace\/?/, '') !== ''
  const resolved: MateriaisTab =
    !hasFileSegment && visibleTabs.some((x) => x.key === matParam) ? (matParam as MateriaisTab) : 'arquivos'

  const [activeTab, setActiveTab] = useState<MateriaisTab>(resolved)

  // ?mat= mudou por fora (back/forward, link colado) → acompanha
  useEffect(() => { setActiveTab(resolved) }, [resolved])

  const selectTab = (tab: MateriaisTab) => {
    setActiveTab(tab)
    if (tab === 'arquivos') setSearchParams({}, { replace: true })
    else setSearchParams({ mat: tab }, { replace: true })
  }

  // Tab bar sempre visível (slim): mesmo na aba Arquivos o editor é tela
  // cheia (h-full), então a barra vive fora do fluxo do FileTree — flex
  // column com flex-shrink-0 não quebra o layout.
  return (
    <div className="flex flex-col h-full min-h-0" style={{ background: 'var(--bg-primary)' }}>
      <PageTabBar ariaLabel="Materiais" slim extraClass="flex-shrink-0" active={activeTab} onSelect={selectTab} tabs={visibleTabs.map((x) => ({ key: x.key, label: t(x.labelKey) }))} />
      <div className="flex-1 min-h-0 overflow-hidden">
        <Suspense fallback={<div className="p-8 text-sm text-[#98A2B3]">Carregando…</div>}>
          {/* O Workspace fica montado (oculto nas outras abas) para não perder
              os tabs abertos/editor no estado ao alternar. */}
          <div className="h-full" style={{ display: activeTab === 'arquivos' ? 'block' : 'none' }}>
            <WorkspacePage />
          </div>
          {activeTab === 'midias' && (
            <div className="h-full overflow-auto p-4 lg:p-6">
              <MediaPage embedded />
            </div>
          )}
          {activeTab === 'shares' && (
            <div className="h-full overflow-auto p-4 lg:p-6">
              <ShareLinksPage embedded />
            </div>
          )}
          {activeTab === 'templates' && (
            <div className="h-full overflow-auto p-4 lg:p-6">
              <TemplatesPage embedded />
            </div>
          )}
        </Suspense>
      </div>
    </div>
  )
}
