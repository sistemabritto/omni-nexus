// Modified 2026-10-15: OmniNexus Live global UI system; original EvoNexus attribution retained.
import { useNavigate } from 'react-router-dom'
import { Cpu, Zap, Terminal, Package, Plug, Database, Brain, Library, DollarSign, Users } from 'lucide-react'
import { useAuth } from '../context/AuthContext'

// Hub "Inteligência" (revamp 19/09): uma porta só para tudo que dá cérebro à
// operação. Cada card navega p/ a página completa já existente (a própria
// página tem botão de volta p/ cá); as rotas antigas (/providers, /skills…)
// continuam válidas e com deep-link; a sidebar mostra os principais e o
// resto fica aqui, tirando item do menu.

const TABS = [
  { id: 'providers', path: '/providers', icon: Cpu, label: 'Provedores (harness→provider→modelo)' },
  { id: 'conhecimento', path: '/knowledge', icon: Database, label: 'Conhecimento (RAG)' },
  { id: 'memoria', path: '/memory', icon: Brain, label: 'Memória' },
  { id: 'mempalace', path: '/mempalace', icon: Library, label: 'MemPalace' },
  { id: 'costs', path: '/costs', icon: DollarSign, label: 'Custos' },
]

const CATALOG = [
  { id: 'agents', path: '/agentes', icon: Users, label: 'Squad de agentes' },
  { id: 'skills', path: '/skills', icon: Zap, label: 'Skills' },
  { id: 'mcp', path: '/mcp-servers', icon: Terminal, label: 'MCP Servers' },
  { id: 'plugins', path: '/plugins', icon: Package, label: 'Plugins' },
  { id: 'integrations', path: '/integrations', icon: Plug, label: 'APIs' },
]

export default function Intelligence() {
  const navigate = useNavigate()
  const { hasPermission } = useAuth()

  const cardClass = (enabled: boolean) =>
    `group flex flex-col gap-2 rounded-xl border p-4 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--evo-green)]/50 ${
      enabled
        ? 'border-[color:var(--border)] bg-[color:var(--bg-card)]/60 hover:border-[color:var(--evo-green)]/50 hover:bg-[color:var(--bg-card)] cursor-pointer'
        : 'border-[color:var(--border)]/40 bg-[#0f1522]/40 opacity-60 cursor-not-allowed'
    }`

  return (
    <div className="max-w-5xl mx-auto">
      <h1 className="text-xl font-semibold text-white mb-1">
        Inteligência
      </h1>
      <p className="text-sm text-[color:var(--text-muted)] mb-6">
        Tudo que dá cérebro à operação — provedores, conhecimento, memória e integrações.
      </p>

      <section className="mb-8">
        <h2 className="text-xs uppercase tracking-wider text-[color:var(--text-muted)] font-semibold mb-3">
          Cérebro & memória
        </h2>
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => tab.path && navigate(tab.path)}
              className={cardClass(!!tab.path)}
            >
              <tab.icon size={20} className="text-[color:var(--evo-green)]" />
              <span className="text-sm font-medium text-[color:var(--text-secondary)]">{tab.label}</span>
            </button>
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-xs uppercase tracking-wider text-[color:var(--text-muted)] font-semibold mb-3">
          Catálogo (disponível para todos os agentes)
        </h2>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {CATALOG.map((tab) => {
            const can = tab.id === 'plugins' || hasPermission(tab.id === 'mcp' ? 'config' : tab.id, 'view')
            return (
              <button
                key={tab.id}
                onClick={() => can && navigate(tab.path)}
                className={cardClass(can)}
              >
                <tab.icon size={20} className="text-[color:var(--evo-green)]" />
                <span className="text-sm font-medium text-[color:var(--text-secondary)]">{tab.label}</span>
              </button>
            )
          })}
        </div>
      </section>
    </div>
  )
}
