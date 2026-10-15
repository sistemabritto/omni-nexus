// Modified 2026-10-15: OmniNexus Live global UI system; original EvoNexus attribution retained.
import { useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'

// Botão de volta ao hub /inteligencia. As páginas do hub (Provedores,
// Conhecimento, Memória, MemPalace, Custos, Skills, MCP, Plugins, APIs)
// abriam sem caminho de volta — quem entrava pelo hub ficava preso
// (encontrado no uso real 20/09).
const HUB_PATH = '/inteligencia'

export default function HubBackLink() {
  const navigate = useNavigate()
  return (
    <button
      onClick={() => navigate(HUB_PATH)}
      className="group inline-flex items-center gap-1.5 text-sm text-[color:var(--text-muted)] hover:text-[color:var(--text-primary)] transition-colors mb-4 -ml-2 px-2 py-1.5 rounded-lg hover:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--evo-green)]/50 cursor-pointer"
    >
      <ArrowLeft size={15} className="transition-transform group-hover:-translate-x-0.5" />
      Inteligência
    </button>
  )
}
