import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X, Upload, Building2 } from 'lucide-react'
import { api } from '../lib/api'
import type { Company } from '../context/CompanyContext'
import { useCompanies } from '../context/CompanyContext'

function slugify(name: string): string {
  return name
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

function formatCnpj(raw: string): string {
  const d = raw.replace(/\D/g, '').slice(0, 14)
  if (d.length <= 2) return d
  if (d.length <= 5) return `${d.slice(0, 2)}.${d.slice(2)}`
  if (d.length <= 8) return `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5)}`
  if (d.length <= 12) return `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8)}`
  return `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8, 12)}-${d.slice(12)}`
}

// W3 (2026-09-21): onboarding de empresa — o MESMO modal cria (company=null)
// e edita. Sem empresa criada nada filtra no dashboard; por isso a criação é
// um caminho primeiro-classe, acessível pelo "+" do seletor do rodapé.
export default function CompanyManagerModal({
  company,
  onClose,
}: {
  company: Company | null
  onClose: () => void
}) {
  const { t } = useTranslation()
  const { reload } = useCompanies()
  const isCreate = company === null
  const [name, setName] = useState(company?.name ?? '')
  const [slug, setSlug] = useState(company?.slug ?? '')
  const [slugTouched, setSlugTouched] = useState(!isCreate)
  const [cnpj, setCnpj] = useState(company?.cnpj ?? '')
  const [domain, setDomain] = useState(company?.domain ?? '')
  const [preview, setPreview] = useState<string | null>(company?.logo_url ?? null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [created, setCreated] = useState<Company | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  async function uploadLogo(file: File) {
    // Em modo criar, upload só depois de existir — salva logo_path via PATCH
    if (!company && !created) return
    const target = created ?? company!
    setBusy(true)
    setError('')
    try {
      const form = new FormData()
      form.append('file', file)
      const res: Company = await api.upload(`/companies/${target.id}/logo`, form)
      setPreview(res.logo_url ?? null)
      await reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : t('nav.companies.selectFile'))
    } finally {
      setBusy(false)
    }
  }

  async function removeLogo() {
    const target = created ?? company
    if (!target) return
    setBusy(true)
    setError('')
    try {
      await api.delete(`/companies/${target.id}/logo`)
      setPreview(null)
      await reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'delete failed')
    } finally {
      setBusy(false)
    }
  }

  async function save(e?: React.FormEvent) {
    e?.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) return setError(t('nav.companies.nameRequired'))
    setBusy(true)
    setError('')
    try {
      if (isCreate) {
        const payload: Record<string, string> = { name: trimmed }
        const finalSlug = slugTouched ? slug : slugify(trimmed)
        if (finalSlug) payload.slug = finalSlug
        if (cnpj.trim()) payload.cnpj = cnpj.trim()
        if (domain.trim()) payload.domain = domain.trim()
        const c: Company = await api.post('/companies', payload)
        setCreated(c)
        await reload()
      } else if (company) {
        const payload: Record<string, unknown> = {}
        if (trimmed !== company.name) payload.name = trimmed
        if (cnpj.trim() !== (company.cnpj ?? '')) payload.cnpj = cnpj.trim() || null
        if (domain.trim() !== (company.domain ?? '')) payload.domain = domain.trim() || null
        if (Object.keys(payload).length > 0) {
          await api.patch(`/companies/${company.id}`, payload)
          await reload()
        }
        onClose()
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err ?? '')
      if (msg.includes('409')) {
        setError(cnpj.trim() && (msg.toLowerCase().includes('cnpj')) ? t('nav.companies.cnpjTaken') : t('nav.companies.slugTaken'))
      } else if (msg.includes('400')) {
        setError(t('nav.companies.nameRequired'))
      } else {
        setError(msg)
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="bg-[#161b22] border border-[#21262d] rounded-xl w-full max-w-sm mx-4 p-5 max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Building2 size={16} className="text-[#00FFA7]" />
            <h2 className="text-sm font-semibold text-white">
              {isCreate ? t('nav.companies.newTitle') : company!.name}
            </h2>
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-white/10 text-[#98A2B3] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#00FFA7]/60">
            <X size={16} />
          </button>
        </div>

        <form onSubmit={save} className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-[#D0D5DD] mb-1">
              {t('nav.companies.nameLabel')}
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => {
                setName(e.target.value)
                if (!slugTouched) setSlug(slugify(e.target.value))
              }}
              placeholder={t('nav.companies.namePlaceholder')}
              autoFocus={isCreate}
              className="w-full bg-[#0d1117] border border-[#30363d] rounded-lg px-3 py-2 text-sm text-white placeholder-[#484f58] focus:border-[#00FFA7] focus:outline-none"
            />
          </div>

          {isCreate && (
            <div>
              <label className="block text-xs font-medium text-[#D0D5DD] mb-1">
                {t('nav.companies.slugLabel')}
              </label>
              <input
                type="text"
                value={slug}
                onChange={(e) => { setSlugTouched(true); setSlug(slugify(e.target.value)) }}
                placeholder={t('nav.companies.slugPlaceholder')}
                className="w-full bg-[#0d1117] border border-[#30363d] rounded-lg px-3 py-2 text-sm text-white placeholder-[#484f58] focus:border-[#00FFA7] focus:outline-none font-mono"
              />
              <p className="text-[10px] text-[#484f58] mt-1">{t('nav.companies.slugHint')}</p>
            </div>
          )}

          <div>
            <label className="block text-xs font-medium text-[#D0D5DD] mb-1">
              {t('nav.companies.cnpjLabel')}
            </label>
            <input
              type="text"
              inputMode="numeric"
              value={cnpj}
              onChange={(e) => setCnpj(formatCnpj(e.target.value))}
              placeholder={t('nav.companies.cnpjPlaceholder')}
              className="w-full bg-[#0d1117] border border-[#30363d] rounded-lg px-3 py-2 text-sm text-white placeholder-[#484f58] focus:border-[#00FFA7] focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-[#D0D5DD] mb-1">
              {t('nav.companies.domainLabel')}
            </label>
            <input
              type="text"
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              placeholder={t('nav.companies.domainPlaceholder')}
              className="w-full bg-[#0d1117] border border-[#30363d] rounded-lg px-3 py-2 text-sm text-white placeholder-[#484f58] focus:border-[#00FFA7] focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-[#D0D5DD] mb-1">
              {t('nav.companies.upload')}
            </label>
            <div className="flex items-center gap-3">
              {preview ? (
                <img src={preview} alt="" className="h-10 w-auto max-w-[120px] object-contain" />
              ) : (
                <div className="h-10 w-10 rounded-md bg-white/5 flex items-center justify-center text-[#484f58]">
                  <Building2 size={18} />
                </div>
              )}
              <input
                ref={fileRef}
                type="file"
                accept=".png,.webp,.jpg,.jpeg,.svg"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0]
                  if (f) uploadLogo(f)
                  e.target.value = ''
                }}
              />
              <button
                type="button"
                disabled={busy || (isCreate && !created)}
                onClick={() => fileRef.current?.click()}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#00FFA7]/15 text-[#00FFA7] text-xs hover:bg-[#00FFA7]/25 disabled:opacity-40 transition-colors"
              >
                <Upload size={13} /> {preview ? t('nav.companies.changeLogo') : t('nav.companies.upload')}
              </button>
              {preview && !isCreate && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={removeLogo}
                  className="px-2 py-1.5 rounded-lg bg-white/5 text-[#98A2B3] text-xs hover:bg-white/10 disabled:opacity-40 transition-colors"
                >
                  {t('nav.companies.removeLogo')}
                </button>
              )}
            </div>
            {isCreate && !created && (
              <p className="text-[10px] text-[#484f58] mt-1">{t('nav.companies.logoAfterCreate')}</p>
            )}
          </div>

          {error && <p className="text-xs text-red-400">{error}</p>}

          {isCreate && created ? (
            <div className="rounded-lg bg-[#00FFA7]/10 border border-[#00FFA7]/30 px-3 py-2.5 text-xs text-[#00FFA7] space-y-2">
              <p>{t('nav.companies.createdMsg', { name: created.name })}</p>
              <p className="text-[#98A2B3]">{t('nav.companies.emptyHint')}</p>
              <button
                type="button"
                onClick={onClose}
                className="w-full px-3 py-2 rounded-lg bg-[#00FFA7] text-black font-semibold text-xs hover:bg-[#00FFA7]/85 transition-colors"
              >
                {t('nav.companies.done')}
              </button>
            </div>
          ) : (
            <button
              type="submit"
              disabled={busy || !name.trim()}
              className="w-full px-3 py-2.5 rounded-lg bg-[#00FFA7] text-black font-semibold text-sm hover:bg-[#00FFA7]/85 disabled:opacity-50 transition-colors"
            >
              {busy ? t('nav.companies.saving') : isCreate ? t('nav.companies.create') : t('nav.companies.save')}
            </button>
          )}
        </form>
      </div>
    </div>
  )
}
