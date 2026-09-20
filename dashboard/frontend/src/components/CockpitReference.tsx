import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, Pencil, X, Check, FileText } from 'lucide-react'
import { api } from '../lib/api'
import Markdown from './Markdown'

/**
 * Reference card — the old "Settings → Reference" tab, condensed into the
 * cockpit. Collapsed by default (it's context, not action); expands to show
 * CLAUDE.md with an inline editor (PUT /api/workspace/file). Makefile targets
 * and commands stay available via the same endpoints when someone asks for
 * them — CLAUDE.md is the document people actually maintain by hand.
 */
export default function CockpitReference() {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(false)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open || content) return
    setLoading(true)
    api.getRaw('/config/claude-md')
      .then((data: string) => setContent(data))
      .catch(() => setContent(''))
      .finally(() => setLoading(false))
  }, [open, content])

  const startEdit = () => { setDraft(content); setEditing(true) }
  const cancelEdit = () => setEditing(false)
  const save = async () => {
    setSaving(true)
    try {
      await api.put('/workspace/file', { path: 'CLAUDE.md', content: draft })
      setContent(draft)
      setEditing(false)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="bg-white/[0.02] border border-white/[0.06] rounded-2xl mb-6">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-5 py-3 text-left"
      >
        <span className="flex items-center gap-2.5 text-sm text-[#8b949e] group">
          <FileText size={14} className="text-[#98A2B3] group-hover:text-[#e6edf3] transition-colors" />
          CLAUDE.md
          <span className="text-[11px] text-[#98A2B3] hidden sm:inline">
            {t('cockpit.referenceHint')}
          </span>
        </span>
        <ChevronDown size={14} className={`text-[#98A2B3] transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="px-5 pb-5">
          {!editing ? (
            <div className="rounded-xl bg-[#0b1018]/60 border border-white/[0.06] max-h-[420px] overflow-y-auto">
              {loading ? (
                <div className="p-4 space-y-2">
                  {[...Array(6)].map((_, i) => <div key={i} className="skeleton h-4 rounded" />)}
                </div>
              ) : (
                <div className="markdown-content p-4 text-[13px]">
                  <Markdown>{content || '—'}</Markdown>
                </div>
              )}
            </div>
          ) : (
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              className="w-full h-[420px] p-4 rounded-xl bg-[#0b1018]/80 border border-[#00FFA7]/20 text-[12px] font-mono text-[#e6edf3] focus:outline-none focus:border-[#00FFA7]/50 resize-y"
              spellCheck={false}
            />
          )}
          <div className="flex items-center gap-2 mt-3">
            {editing ? (
              <>
                <button onClick={save} disabled={saving}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#00FFA7] text-[#080c14] text-xs font-semibold hover:bg-[#00e69a] disabled:opacity-40 transition-colors">
                  <Check size={13} /> {t('cockpit.referenceSave')}
                </button>
                <button onClick={cancelEdit}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-white/[0.1] text-xs text-[#8b949e] hover:text-[#e6edf3] transition-colors">
                  <X size={13} /> {t('cockpit.referenceCancel')}
                </button>
              </>
            ) : (
              <button onClick={startEdit} disabled={!content}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-white/[0.1] text-xs text-[#8b949e] hover:text-[#e6edf3] disabled:opacity-40 transition-colors">
                <Pencil size={13} /> {t('cockpit.referenceEdit')}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
