// Modified 2026-10-15: OmniNexus Live global UI system; original EvoNexus attribution retained.
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X, Pencil, Trash2, Building2, AlertTriangle } from 'lucide-react'
import DialogFrame from './DialogFrame'
import { api } from '../lib/api'
import type { Company } from '../context/CompanyContext'
import { useCompanies } from '../context/CompanyContext'
import CompanyManagerModal from './CompanyManagerModal'

export default function CompanyListModal({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation()
  const { companies, activeCompanyId, reload, setActiveCompanyId } = useCompanies()
  const [editing, setEditing] = useState<Company | null>(null)
  const [deleting, setDeleting] = useState<Company | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function doDelete(c: Company) {
    setBusy(true)
    setError('')
    try {
      await api.delete(`/companies/${c.id}`)
      if (activeCompanyId === c.id) setActiveCompanyId(null)
      await reload()
      setDeleting(null)
      setConfirmDelete(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : '')
    } finally {
      setBusy(false)
    }
  }

  return (
    <DialogFrame label={t('nav.companies.manageAll')} onClose={onClose} busy={busy}>
      <div
        className="p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Building2 size={16} className="text-[color:var(--evo-green)]" />
            <h2 className="text-sm font-semibold text-white">{t('nav.companies.manageAll')}</h2>
          </div>
          <button aria-label={t('common.close')} disabled={busy} onClick={onClose} className="p-1 rounded hover:bg-white/10 text-[color:var(--text-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--evo-green)]/60">
            <X size={16} />
          </button>
        </div>

        <div className="space-y-2">
          {companies.map((c) => (
            <div key={c.id} className={`rounded-lg border p-3 ${activeCompanyId === c.id ? 'border-[color:var(--evo-green)]/40 bg-[color:var(--evo-green)]/5' : 'border-[#30363d]'}`}>
              <div className="flex items-center gap-3">
                {c.logo_url ? (
                  <img src={c.logo_url} alt="" className="h-9 w-9 rounded-lg object-cover shrink-0" />
                ) : (
                  <div className="h-9 w-9 rounded-lg bg-white/5 flex items-center justify-center text-[color:var(--text-muted)] shrink-0">
                    <Building2 size={16} />
                  </div>
                )}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-white truncate">{c.name}</p>
                  <p className="text-[11px] text-[color:var(--text-muted)] truncate">{c.slug}{c.cnpj ? ` · ${c.cnpj}` : ''}{c.domain ? ` · ${c.domain}` : ''}</p>
                </div>
                <div className="flex gap-1 shrink-0">
                  <button
                    onClick={() => setEditing(c)}
                    aria-label={`${t('nav.companies.edit')} ${c.name}`} title={t('nav.companies.edit')}
                    className="p-1.5 rounded-lg bg-white/5 text-[color:var(--text-muted)] hover:text-[color:var(--text-secondary)] hover:bg-white/10 transition-colors"
                  >
                    <Pencil size={14} />
                  </button>
                  <button
                    onClick={() => { setDeleting(c); setConfirmDelete(false); setError('') }}
                    aria-label={`${t('nav.companies.delete')} ${c.name}`} title={t('nav.companies.delete')}
                    className="p-1.5 rounded-lg bg-white/5 text-[color:var(--text-muted)] hover:text-red-400 hover:bg-red-500/10 transition-colors"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            </div>
          ))}

          {companies.length === 0 && (
            <p className="text-xs text-[color:var(--text-muted)] text-center py-6">{t('nav.companies.noneYet')}</p>
          )}
        </div>

        {error && !deleting && <p role="alert" className="text-xs text-red-400 mt-3">{error}</p>}

        {/* 2-stage delete confirm */}
        {deleting && (
          <DialogFrame label={t(confirmDelete ? 'nav.companies.deleteFinal' : 'nav.companies.deleteTitle')} onClose={() => setDeleting(null)} busy={busy} size="small" initialFocusSelector="[data-dialog-cancel]">
            <div className="p-5" onClick={(e) => e.stopPropagation()}>
              {error && <p role="alert" className="text-xs text-red-400 mb-3">{error}</p>}
              {!confirmDelete ? (
                <>
                  <div className="flex items-center gap-2 mb-3">
                    <AlertTriangle size={16} className="text-amber-400" />
                    <h3 className="text-sm font-semibold text-white">{t('nav.companies.deleteTitle')}</h3>
                  </div>
                  <p className="text-xs text-[color:var(--text-muted)] mb-4">
                    {t('nav.companies.deleteMsg', { name: deleting.name })}
                  </p>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setConfirmDelete(true)}
                      disabled={busy}
                      className="flex-1 px-3 py-2 rounded-lg bg-red-500/15 text-red-400 text-xs font-medium hover:bg-red-500/25 disabled:opacity-50 transition-colors"
                    >
                      {t('nav.companies.deleteConfirm')}
                    </button>
                    <button data-dialog-cancel
                      onClick={() => setDeleting(null)}
                      className="flex-1 px-3 py-2 rounded-lg bg-white/5 text-[color:var(--text-muted)] text-xs hover:bg-white/10 transition-colors"
                    >
                      {t('nav.companies.cancel')}
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <div className="flex items-center gap-2 mb-3">
                    <AlertTriangle size={16} className="text-red-400" />
                    <h3 className="text-sm font-semibold text-white">{t('nav.companies.deleteFinal')}</h3>
                  </div>
                  <p className="text-xs text-[color:var(--text-muted)] mb-4">
                    {t('nav.companies.deleteFinalMsg', { name: deleting.name })}
                  </p>
                  <div className="flex gap-2">
                    <button
                      onClick={() => doDelete(deleting)}
                      disabled={busy}
                      className="flex-1 px-3 py-2 rounded-lg bg-red-500 text-white text-xs font-semibold hover:bg-red-500/85 disabled:opacity-50 transition-colors"
                    >
                      {busy ? t('nav.companies.deleting') : t('nav.companies.deleteGo')}
                    </button>
                    <button data-dialog-cancel
                      onClick={() => setDeleting(null)}
                      disabled={busy}
                      className="flex-1 px-3 py-2 rounded-lg bg-white/5 text-[color:var(--text-muted)] text-xs hover:bg-white/10 disabled:opacity-50 transition-colors"
                    >
                      {t('nav.companies.cancel')}
                    </button>
                  </div>
                </>
              )}
            </div>
          </DialogFrame>
        )}
      </div>

      {editing && (
        <CompanyManagerModal
          company={editing}
          onClose={() => { setEditing(null); reload() }}
        />
      )}
    </DialogFrame>
  )
}
