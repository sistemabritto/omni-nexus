import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X, Upload } from 'lucide-react'
import { api } from '../lib/api'
import type { Company } from '../context/CompanyContext'
import { useCompanies } from '../context/CompanyContext'

export default function CompanyManagerModal({
  company,
  onClose,
}: {
  company: Company
  onClose: () => void
}) {
  const { t } = useTranslation()
  const { reload } = useCompanies()
  const [preview, setPreview] = useState<string | null>(company.logo_url ?? null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  async function uploadFile(file: File) {
    setBusy(true)
    setError('')
    try {
      const form = new FormData()
      form.append('file', file)
      const res: Company = await api.upload(`/companies/${company.id}/logo`, form)
      setPreview(res.logo_url ?? null)
      await reload()
    } catch (e: any) {
      setError(e?.message || 'upload failed')
    } finally {
      setBusy(false)
    }
  }

  async function removeLogo() {
    setBusy(true)
    setError('')
    try {
      await api.delete(`/companies/${company.id}/logo`)
      setPreview(null)
      await reload()
    } catch (e: any) {
      setError(e?.message || 'delete failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="bg-[#161b22] border border-[#21262d] rounded-xl w-full max-w-sm mx-4 p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-white">{company.name}</h2>
          <button onClick={onClose} className="p-1 rounded hover:bg-white/10 text-[#98A2B3]">
            <X size={16} />
          </button>
        </div>

        <div className="flex flex-col items-center gap-3">
          <img
            src={preview ?? '/EVO_NEXUS.webp'}
            alt=""
            className="h-14 w-auto max-w-[180px] object-contain"
          />
          <input
            ref={fileRef}
            type="file"
            accept=".png,.webp,.jpg,.jpeg,.svg"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) uploadFile(f)
              e.target.value = ''
            }}
          />
          <div className="flex items-center gap-2">
            <button
              disabled={busy}
              onClick={() => fileRef.current?.click()}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#00FFA7]/15 text-[#00FFA7] text-xs hover:bg-[#00FFA7]/25 disabled:opacity-50"
            >
              <Upload size={13} /> {t('companies.upload')}
            </button>
            {company.logo_url && (
              <button
                disabled={busy}
                onClick={removeLogo}
                className="px-3 py-1.5 rounded-lg bg-white/5 text-[#98A2B3] text-xs hover:bg-white/10 disabled:opacity-50"
              >
                {t('companies.removeLogo')}
              </button>
            )}
          </div>
          <p className="text-[10px] text-[#98A2B3]">{t('companies.selectFile')}</p>
          {error && <p className="text-xs text-red-400">{error}</p>}
        </div>
      </div>
    </div>
  )
}
