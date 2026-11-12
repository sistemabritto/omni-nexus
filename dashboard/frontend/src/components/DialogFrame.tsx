// Added 2026-10-15: accessible top-layer dialogs; retains EvoNexus content and actions.
import { useEffect, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import './DialogFrame.css'

export default function DialogFrame({ label, onClose, children, size = 'medium', busy = false, initialFocusSelector }: {
  label: string
  onClose: () => void
  children: ReactNode
  size?: 'small' | 'medium'
  busy?: boolean
  initialFocusSelector?: string
}) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    const active = document.activeElement
    const previous = active instanceof HTMLElement && active !== document.body && !dialog.contains(active) ? active : null
    dialog.showModal()
    return () => {
      if (dialog.open) dialog.close()
      if (previous?.isConnected && !previous.closest('[inert]')) previous.focus()
      else {
        const parent = Array.from(document.querySelectorAll<HTMLDialogElement>('dialog[data-omni-modal][open]')).at(-1)
        const fallback = parent?.querySelector<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled)')
          || document.querySelector<HTMLElement>('#omn-navigation:not([inert]) button[aria-haspopup="menu"]')
        fallback?.focus()
      }
    }
  }, [])
  useEffect(() => {
    if (initialFocusSelector && ref.current?.open) ref.current.querySelector<HTMLElement>(initialFocusSelector)?.focus()
  }, [label, initialFocusSelector])
  return createPortal(<dialog ref={ref} data-omni-modal data-size={size} className="omn-dialog" aria-label={label} aria-busy={busy}
    onKeyDown={event => {
      if (event.key !== 'Tab') return
      const top = Array.from(document.querySelectorAll('dialog[data-omni-modal][open]')).at(-1)
      if (top !== event.currentTarget) return
      event.stopPropagation()
      const controls = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex="0"]'))
        .filter(element => element.getClientRects().length > 0)
      const first = controls[0], last = controls.at(-1)
      if (!first) { event.preventDefault(); event.currentTarget.focus() }
      else if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }}
    onCancel={event => { event.preventDefault(); event.stopPropagation(); if (!busy) onClose() }}
    onClick={event => {
      if (busy || event.target !== event.currentTarget) return
      const box = event.currentTarget.getBoundingClientRect()
      if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) onClose()
    }}>
    {children}
  </dialog>, document.body)
}
