// Modified 2026-10-15: OmniNexus Live global UI system; original EvoNexus attribution retained.
import { useState } from 'react'
import { AlertTriangle } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../../../context/AuthContext'

const inp = "w-full px-4 py-3 rounded-lg bg-[color:var(--bg-card)] border border-[color:var(--border)] text-[#e2e8f0] placeholder-[#3d4f65] text-sm transition-colors duration-200 focus:outline-none focus:border-[color:var(--evo-green)]/60 focus:ring-1 focus:ring-[color:var(--evo-green)]/20"

interface SelectedSnapshot {
  ref: string
  label: string
  includeKb: boolean
}

interface RestoreConfirmProps {
  snapshot: SelectedSnapshot
  onConfirm: () => void
  onBack: () => void
}

export default function RestoreConfirm({ snapshot, onConfirm, onBack }: RestoreConfirmProps) {
  const { t } = useTranslation()
  const { user } = useAuth()
  const workspaceName = user?.username || 'workspace'
  const [confirm, setConfirm] = useState('')

  const isMatch = confirm.trim().toLowerCase() === workspaceName.toLowerCase()

  return (
    <div className="min-h-screen bg-[color:var(--bg-primary)] flex items-center justify-center px-4 font-[family-name:var(--sb-font-body)]">
      <div className="w-full max-w-[480px] relative z-10">
        <div className="rounded-xl border border-[color:var(--border)] bg-[color:var(--bg-card)] shadow-[0_4px_40px_rgba(0,0,0,0.4)]">
          <div className="px-7 pt-7 pb-5 border-b border-[color:var(--border)]">
            <div className="flex items-center gap-3">
              <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-[#3a1515] border border-[#5a2020]">
                <AlertTriangle size={18} className="text-[#f87171]" />
              </div>
              <div>
                <h2 className="text-[16px] font-semibold text-[#e2e8f0]">{t('restore.confirm.title')}</h2>
                <p className="text-[11px] text-[color:var(--text-muted)] mt-0.5">{t('restore.confirm.subtitle')}</p>
              </div>
            </div>
          </div>

          <div className="px-7 py-6 space-y-4">
            <div className="p-3 rounded-lg bg-[#1a0a0a] border border-[#3a1515]">
              <p className="text-[11px] text-[#f87171] leading-relaxed">
                {t('restore.confirm.warningPart1')}
                <span className="font-semibold">{snapshot.label}</span>
                {'.'}
                {snapshot.includeKb && (
                  <span>{t('restore.confirm.warningKb')}</span>
                )}
              </p>
            </div>

            <div>
              <label className="block text-[11px] font-semibold text-[color:var(--text-muted)] mb-1.5 tracking-[0.08em] uppercase">
                {t('restore.confirm.typeToConfirmPart1')}
                <span className="text-[#e2e8f0]">{workspaceName}</span>
                {t('restore.confirm.typeToConfirmPart2')}
              </label>
              <input
                type="text"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                className={inp}
                placeholder={workspaceName}
                autoFocus
              />
            </div>

            <div className="flex gap-3 pt-2">
              <button
                onClick={onBack}
                className="flex-none py-3 px-4 rounded-lg border border-[color:var(--border)] text-[color:var(--text-muted)] hover:border-[color:var(--evo-green)]/30 hover:text-[#e2e8f0] text-sm font-medium transition-colors"
              >
                {t('restore.back')}
              </button>
              <button
                onClick={onConfirm}
                disabled={!isMatch}
                className="flex-1 py-3 rounded-lg bg-[#f87171] text-[#1a0a0a] hover:bg-[#ef4444] text-sm font-semibold transition-colors disabled:opacity-40"
              >
                {t('restore.confirm.restoreBtn')}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
