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
      className="group inline-flex items-center gap-1.5 text-sm text-[#98A2B3] hover:text-[#e6edf3] transition-colors mb-4 -ml-2 px-2 py-1.5 rounded-lg hover:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#00FFA7]/50 cursor-pointer"
    >
      <ArrowLeft size={15} className="transition-transform group-hover:-translate-x-0.5" />
      Inteligência
    </button>
  )
}
