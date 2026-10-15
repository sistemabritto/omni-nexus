// Modified 2026-10-15: OmniNexus Live global UI system; original EvoNexus attribution retained.
import { useRef } from 'react'

// Barra de abas padrão do dashboard (ui-ux-pro-max: consistent interaction
// states + keyboard navigation). Cockpit (/), Materiais (/workspace) e
// Configurações (/settings) usam esta MESMA barra: mesmo idioma visual
// (underline verde), aria completo, setas ← → navegam entre abas, focus
// visível. Cada página controla active/onSelect (deep-link por ?tab=/?mat=).
export interface PageTabBarTab<K extends string> {
  key: K
  label: string
}

export default function PageTabBar<K extends string>({
  ariaLabel,
  tabs,
  active,
  onSelect,
  slim = false,
  extraClass = '',
}: {
  ariaLabel: string
  tabs: PageTabBarTab<K>[]
  active: K
  onSelect: (key: K) => void
  slim?: boolean
  extraClass?: string
}) {
  const refs = useRef<Map<K, HTMLButtonElement>>(new Map())

  const focusTab = (key: K) => {
    const btn = refs.current.get(key)
    if (!btn) return
    btn.focus()
    onSelect(key)
  }

  const onKeyDown = (e: React.KeyboardEvent, index: number) => {
    let next: number | null = null
    if (e.key === 'ArrowRight') next = (index + 1) % tabs.length
    else if (e.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length
    else if (e.key === 'Home') next = 0
    else if (e.key === 'End') next = tabs.length - 1
    if (next !== null) {
      e.preventDefault()
      focusTab(tabs[next].key)
    }
  }

  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className={`flex gap-1 border-b border-[color:var(--border)] overflow-x-auto ${extraClass}`}
    >
      {tabs.map((tab, i) => (
        <button
          key={tab.key}
          ref={(el) => {
            if (el) refs.current.set(tab.key, el)
            else refs.current.delete(tab.key)
          }}
          role="tab"
          aria-selected={active === tab.key}
          tabIndex={active === tab.key ? 0 : -1}
          onClick={() => onSelect(tab.key)}
          onKeyDown={(e) => onKeyDown(e, i)}
          className={`px-4 font-medium whitespace-nowrap transition-colors border-b-2 -mb-px cursor-pointer
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--evo-green)]/50 rounded-t-md
            ${slim ? 'py-1.5 text-[13px]' : 'py-2.5 text-sm'}
            ${
              active === tab.key
                ? 'text-[color:var(--evo-green)] border-[color:var(--evo-green)]'
                : 'text-[color:var(--text-muted)] border-transparent hover:text-[color:var(--text-primary)] hover:border-[color:var(--border)]'
            }`}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}
