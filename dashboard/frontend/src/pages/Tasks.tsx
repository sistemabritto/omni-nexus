// Modified 2026-10-15: OmniNexus Live global UI system; original EvoNexus attribution retained.
import { useEffect, useState } from 'react'
import { useToast } from '../components/Toast'
import { useConfirm } from '../components/ConfirmDialog'
import { CalendarClock, Plus, Play, X, Eye, RefreshCw, Pencil, Trash2 } from 'lucide-react'
import { api } from '../lib/api'
import { useTranslation } from 'react-i18next'

interface Task {
  id: number
  name: string
  description: string | null
  type: string
  payload: string
  agent: string | null
  scheduled_at: string
  status: string
  created_at: string
  started_at: string | null
  completed_at: string | null
  result_summary: string | null
  error: string | null
  created_by: number | null
}

const STATUS_STYLES: Record<string, { bg: string; text: string; dot: string }> = {
  pending: { bg: 'bg-yellow-500/10 border-yellow-500/20', text: 'text-yellow-400', dot: 'bg-yellow-400' },
  running: { bg: 'bg-blue-500/10 border-blue-500/20', text: 'text-blue-400', dot: 'bg-blue-400 animate-pulse' },
  completed: { bg: 'bg-[color:var(--evo-green)]/10 border-[color:var(--evo-green)]/20', text: 'text-[color:var(--evo-green)]', dot: 'bg-[color:var(--evo-green)]' },
  failed: { bg: 'bg-red-500/10 border-red-500/20', text: 'text-red-400', dot: 'bg-red-400' },
  cancelled: { bg: 'bg-[#667085]/10 border-[#667085]/20', text: 'text-[color:var(--text-muted)]', dot: 'bg-[#667085]' },
}

const TYPE_STYLES: Record<string, string> = {
  skill: 'bg-purple-500/10 border-purple-500/20 text-purple-400',
  prompt: 'bg-blue-500/10 border-blue-500/20 text-blue-400',
  script: 'bg-orange-500/10 border-orange-500/20 text-orange-400',
}

const AGENTS = [
  '', 'clawdia-assistant', 'flux-financeiro', 'atlas-project', 'kai-personal-assistant',
  'pulse-community', 'sage-strategy', 'pixel-social-media', 'nex-comercial', 'mentor-courses',
]

const AGENT_LABELS: Record<string, string> = {
  '': 'None',
  'clawdia-assistant': '@clawdia',
  'flux-financeiro': '@flux',
  'atlas-project': '@atlas',
  'kai-personal-assistant': '@kai',
  'pulse-community': '@pulse',
  'sage-strategy': '@sage',
  'pixel-social-media': '@pixel',
  'nex-comercial': '@nex',
  'mentor-courses': '@mentor',
}

function formatDate(iso: string | null): string {
  if (!iso) return '--'
  const d = new Date(iso)
  return d.toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo', day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' })
}

const emptyForm = { name: '', description: '', type: 'skill', payload: '', agent: '', scheduled_at: '' }

export default function Tasks() {
  const { t } = useTranslation()
  const toast = useToast()
  const confirm = useConfirm()
  const [tasks, setTasks] = useState<Task[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<string>('')
  const [showModal, setShowModal] = useState(false)
  const [editingTask, setEditingTask] = useState<Task | null>(null)
  const [form, setForm] = useState(emptyForm)
  const [saving, setSaving] = useState(false)
  const [viewTask, setViewTask] = useState<Task | null>(null)

  const fetchTasks = () => {
    const params = filter ? `?status=${filter}` : ''
    api.get(`/tasks${params}`)
      .then((data) => {
        setTasks(data.tasks || [])
        setTotal(data.total || 0)
      })
      .catch(() => setTasks([]))
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchTasks() }, [filter])

  const openCreate = () => {
    setEditingTask(null)
    setForm(emptyForm)
    setShowModal(true)
  }

  const openEdit = (task: Task) => {
    setEditingTask(task)
    setForm({
      name: task.name,
      description: task.description || '',
      type: task.type,
      payload: task.payload,
      agent: task.agent || '',
      scheduled_at: task.scheduled_at ? task.scheduled_at.slice(0, 16) : '',
    })
    setShowModal(true)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const body = {
        ...form,
        scheduled_at: form.scheduled_at ? new Date(form.scheduled_at).toISOString() : '',
        agent: form.agent || null,
        description: form.description || null,
      }
      if (editingTask) {
        await api.put(`/tasks/${editingTask.id}`, body)
      } else {
        await api.post('/tasks', body)
      }
      setShowModal(false)
      setLoading(true)
      fetchTasks()
    } catch (e) {
      toast.error('Erro ao salvar tarefa', String(e))
    }
    setSaving(false)
  }

  const handleCancel = async (id: number) => {
    const ok = await confirm({
      title: 'Cancelar tarefa',
      description: 'Cancelar esta tarefa agendada?',
      confirmText: 'Cancelar tarefa',
      variant: 'danger',
    })
    if (!ok) return
    try {
      await api.delete(`/tasks/${id}`)
      fetchTasks()
    } catch (e) {
      toast.error('Erro ao cancelar', String(e))
    }
  }

  const handleRunNow = async (id: number) => {
    try {
      await api.post(`/tasks/${id}/run`)
      fetchTasks()
    } catch (e) {
      toast.error('Erro ao executar', String(e))
    }
  }

  const handleDelete = async (id: number) => {
    const ok = await confirm({
      title: 'Deletar tarefa',
      description: 'Deletar esta tarefa permanentemente?',
      confirmText: 'Deletar',
      variant: 'danger',
    })
    if (!ok) return
    try {
      await api.delete(`/tasks/${id}`)
      fetchTasks()
    } catch (e) {
      toast.error('Erro ao deletar', String(e))
    }
  }

  const filters = [
    { label: 'All', value: '' },
    { label: 'Pending', value: 'pending' },
    { label: 'Running', value: 'running' },
    { label: 'Completed', value: 'completed' },
    { label: 'Failed', value: 'failed' },
  ]

  if (loading) {
    return (
      <div>
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-[color:var(--text-primary)]">{t('tasks.title')}</h1>
        </div>
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => <div key={i} className="skeleton h-16 rounded-xl" />)}
        </div>
      </div>
    )
  }

  return (
    <div>
      {/* Header */}
      <div className="omn-responsive-toolbar flex items-center justify-between mb-8">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-[color:var(--bg-card)] border border-[color:var(--border)] flex items-center justify-center">
            <CalendarClock size={20} className="text-[color:var(--evo-green)]" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-[color:var(--text-primary)]">{t('tasks.title')}</h1>
            <p className="text-[color:var(--text-muted)] mt-0.5 text-sm">One-off scheduled actions</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => { setLoading(true); fetchTasks() }}
            className="flex items-center gap-2 px-3 py-2 rounded-lg border border-[color:var(--border)] bg-[color:var(--bg-card)] text-[color:var(--text-muted)] hover:text-[color:var(--evo-green)] hover:border-[color:var(--evo-green)]/30 transition-colors"
          >
            <RefreshCw size={16} />
          </button>
          <button
            onClick={openCreate}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[color:var(--evo-green)]/10 border border-[color:var(--evo-green)]/20 text-[color:var(--evo-green)] hover:bg-[color:var(--evo-green)]/20 transition-colors font-medium text-sm"
          >
            <Plus size={16} /> New Task
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        {filters.map((f) => (
          <button
            key={f.value}
            onClick={() => { setFilter(f.value); setLoading(true) }}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors border ${
              filter === f.value
                ? 'bg-[color:var(--evo-green)]/10 border-[color:var(--evo-green)]/20 text-[color:var(--evo-green)]'
                : 'bg-[color:var(--bg-card)] border-[color:var(--border)] text-[color:var(--text-muted)] hover:text-[color:var(--text-primary)] hover:border-[color:var(--border)]'
            }`}
          >
            {f.label}
          </button>
        ))}
        <span className="text-[11px] text-[color:var(--text-muted)] ml-2">{total} tasks</span>
      </div>

      {/* Table */}
      {tasks.length === 0 ? (
        <div className="bg-[color:var(--bg-card)] border border-[color:var(--border)] rounded-xl p-12 text-center">
          <CalendarClock size={32} className="text-[color:var(--text-muted)] mx-auto mb-3" />
          <p className="text-[color:var(--text-muted)] text-sm">No scheduled tasks yet</p>
          <button onClick={openCreate} className="mt-3 text-[color:var(--evo-green)] text-sm hover:underline">
            Create your first task
          </button>
        </div>
      ) : (
        <div className="bg-[color:var(--bg-card)] border border-[color:var(--border)] rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[color:var(--text-muted)] text-xs uppercase tracking-wider bg-[color:var(--bg-primary)]/50 border-b border-[color:var(--border)]">
                <th className="text-left p-4 font-medium">Task</th>
                <th className="text-left p-4 font-medium">Type</th>
                <th className="text-left p-4 font-medium">Agent</th>
                <th className="text-left p-4 font-medium">Scheduled</th>
                <th className="text-left p-4 font-medium">Status</th>
                <th className="text-right p-4 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((task) => {
                const st = STATUS_STYLES[task.status] || STATUS_STYLES.pending
                return (
                  <tr key={task.id} className="border-t border-[color:var(--border)]/50 hover:bg-white/[0.02] transition-colors">
                    <td className="p-4">
                      <div className="text-[color:var(--text-primary)] font-medium">{task.name}</div>
                      {task.description && (
                        <div className="text-[color:var(--text-muted)] text-xs mt-0.5 truncate max-w-[300px]">{task.description}</div>
                      )}
                    </td>
                    <td className="p-4">
                      <span className={`inline-flex text-[10px] font-medium px-2 py-0.5 rounded-full border ${TYPE_STYLES[task.type] || ''}`}>
                        {task.type}
                      </span>
                    </td>
                    <td className="p-4">
                      {task.agent ? (
                        <span className="inline-flex text-[11px] font-medium px-2.5 py-0.5 rounded-full bg-[color:var(--evo-green)]/8 border border-[color:var(--evo-green)]/20 text-[color:var(--evo-green)]">
                          {AGENT_LABELS[task.agent] || `@${task.agent}`}
                        </span>
                      ) : (
                        <span className="text-[color:var(--text-muted)]">--</span>
                      )}
                    </td>
                    <td className="p-4 text-[color:var(--text-primary)] text-xs font-mono">{formatDate(task.scheduled_at)}</td>
                    <td className="p-4">
                      <span className={`inline-flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-0.5 rounded-full border ${st.bg} ${st.text}`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${st.dot}`} />
                        {task.status}
                      </span>
                    </td>
                    <td className="p-4">
                      <div className="flex items-center gap-1 justify-end">
                        {task.status === 'pending' && (
                          <>
                            <button onClick={() => handleRunNow(task.id)} className="p-1.5 rounded-lg hover:bg-[color:var(--evo-green)]/10 text-[color:var(--text-muted)] hover:text-[color:var(--evo-green)] transition-colors" title="Run Now">
                              <Play size={14} />
                            </button>
                            <button onClick={() => openEdit(task)} className="p-1.5 rounded-lg hover:bg-white/5 text-[color:var(--text-muted)] hover:text-[color:var(--text-primary)] transition-colors" title="Edit">
                              <Pencil size={14} />
                            </button>
                            <button onClick={() => handleCancel(task.id)} className="p-1.5 rounded-lg hover:bg-red-500/10 text-[color:var(--text-muted)] hover:text-red-400 transition-colors" title="Cancel">
                              <X size={14} />
                            </button>
                          </>
                        )}
                        {(task.status === 'completed' || task.status === 'failed') && (
                          <>
                            <button onClick={() => setViewTask(task)} className="p-1.5 rounded-lg hover:bg-white/5 text-[color:var(--text-muted)] hover:text-[color:var(--text-primary)] transition-colors" title="View Result">
                              <Eye size={14} />
                            </button>
                            <button onClick={() => handleDelete(task.id)} className="p-1.5 rounded-lg hover:bg-red-500/10 text-[color:var(--text-muted)] hover:text-red-400 transition-colors" title="Delete">
                              <Trash2 size={14} />
                            </button>
                          </>
                        )}
                        {task.status === 'failed' && (
                          <button onClick={() => handleRunNow(task.id)} className="p-1.5 rounded-lg hover:bg-[color:var(--evo-green)]/10 text-[color:var(--text-muted)] hover:text-[color:var(--evo-green)] transition-colors" title="Retry">
                            <RefreshCw size={14} />
                          </button>
                        )}
                        {task.status === 'cancelled' && (
                          <button onClick={() => handleDelete(task.id)} className="p-1.5 rounded-lg hover:bg-red-500/10 text-[color:var(--text-muted)] hover:text-red-400 transition-colors" title="Delete">
                            <Trash2 size={14} />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Create/Edit Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={() => setShowModal(false)}>
          <div className="bg-[color:var(--bg-card)] border border-[color:var(--border)] rounded-xl w-full max-w-lg" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-6 py-4 border-b border-[color:var(--border)]">
              <h2 className="text-lg font-semibold text-[color:var(--text-primary)]">
                {editingTask ? 'Edit Task' : 'New Scheduled Task'}
              </h2>
              <button onClick={() => setShowModal(false)} className="p-1 rounded-lg hover:bg-white/5 text-[color:var(--text-muted)] hover:text-[color:var(--text-primary)]">
                <X size={18} />
              </button>
            </div>

            <div className="p-6 space-y-4">
              <div>
                <label className="block text-xs font-medium text-[color:var(--text-muted)] mb-1.5">Name *</label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="e.g. Post LinkedIn about Summit"
                  className="w-full px-3 py-2 bg-[color:var(--bg-primary)] border border-[color:var(--border)] rounded-lg text-sm text-[color:var(--text-primary)] placeholder-[#667085] focus:border-[color:var(--evo-green)]/50 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-[color:var(--text-muted)] mb-1.5">Description</label>
                <input
                  type="text"
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  placeholder="Optional context"
                  className="w-full px-3 py-2 bg-[color:var(--bg-primary)] border border-[color:var(--border)] rounded-lg text-sm text-[color:var(--text-primary)] placeholder-[#667085] focus:border-[color:var(--evo-green)]/50 focus:outline-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-[color:var(--text-muted)] mb-1.5">Type *</label>
                  <select
                    value={form.type}
                    onChange={(e) => setForm({ ...form, type: e.target.value })}
                    className="w-full px-3 py-2 bg-[color:var(--bg-primary)] border border-[color:var(--border)] rounded-lg text-sm text-[color:var(--text-primary)] focus:border-[color:var(--evo-green)]/50 focus:outline-none"
                  >
                    <option value="skill">Skill</option>
                    <option value="prompt">Prompt</option>
                    <option value="script">Script</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-[color:var(--text-muted)] mb-1.5">Agent</label>
                  <select
                    value={form.agent}
                    onChange={(e) => setForm({ ...form, agent: e.target.value })}
                    className="w-full px-3 py-2 bg-[color:var(--bg-primary)] border border-[color:var(--border)] rounded-lg text-sm text-[color:var(--text-primary)] focus:border-[color:var(--evo-green)]/50 focus:outline-none"
                  >
                    {AGENTS.map((a) => (
                      <option key={a} value={a}>{AGENT_LABELS[a] || a}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-[color:var(--text-muted)] mb-1.5">
                  {form.type === 'skill' ? 'Skill name + args' : form.type === 'prompt' ? 'Prompt text' : 'Script path (relative to ADWs/routines/)'} *
                </label>
                <textarea
                  value={form.payload}
                  onChange={(e) => setForm({ ...form, payload: e.target.value })}
                  placeholder={
                    form.type === 'skill' ? 'social-post-writer LinkedIn post about...'
                      : form.type === 'prompt' ? 'Generate a summary of...'
                        : 'custom/my_script.py'
                  }
                  rows={3}
                  className="w-full px-3 py-2 bg-[color:var(--bg-primary)] border border-[color:var(--border)] rounded-lg text-sm text-[color:var(--text-primary)] placeholder-[#667085] focus:border-[color:var(--evo-green)]/50 focus:outline-none font-mono resize-none"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-[color:var(--text-muted)] mb-1.5">Scheduled At *</label>
                <input
                  type="datetime-local"
                  value={form.scheduled_at}
                  onChange={(e) => setForm({ ...form, scheduled_at: e.target.value })}
                  className="w-full px-3 py-2 bg-[color:var(--bg-primary)] border border-[color:var(--border)] rounded-lg text-sm text-[color:var(--text-primary)] focus:border-[color:var(--evo-green)]/50 focus:outline-none"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-[color:var(--border)]">
              <button
                onClick={() => setShowModal(false)}
                className="px-4 py-2 rounded-lg border border-[color:var(--border)] text-[color:var(--text-muted)] hover:text-[color:var(--text-primary)] hover:border-[color:var(--border)] transition-colors text-sm"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={saving || !form.name || !form.payload || !form.scheduled_at}
                className="px-4 py-2 rounded-lg bg-[color:var(--evo-green)]/10 border border-[color:var(--evo-green)]/20 text-[color:var(--evo-green)] hover:bg-[color:var(--evo-green)]/20 transition-colors text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {saving ? 'Saving...' : editingTask ? 'Update' : 'Schedule'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* View Result Modal */}
      {viewTask && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={() => setViewTask(null)}>
          <div className="bg-[color:var(--bg-card)] border border-[color:var(--border)] rounded-xl w-full max-w-2xl max-h-[80vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-6 py-4 border-b border-[color:var(--border)]">
              <div>
                <h2 className="text-lg font-semibold text-[color:var(--text-primary)]">{viewTask.name}</h2>
                <p className="text-xs text-[color:var(--text-muted)] mt-0.5">
                  {viewTask.status === 'completed' ? 'Completed' : 'Failed'} at {formatDate(viewTask.completed_at)}
                  {viewTask.started_at && viewTask.completed_at && (
                    <> — {Math.round((new Date(viewTask.completed_at).getTime() - new Date(viewTask.started_at).getTime()) / 1000)}s</>
                  )}
                </p>
              </div>
              <button onClick={() => setViewTask(null)} className="p-1 rounded-lg hover:bg-white/5 text-[color:var(--text-muted)] hover:text-[color:var(--text-primary)]">
                <X size={18} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              <div>
                <label className="block text-xs font-medium text-[color:var(--text-muted)] mb-1">Payload</label>
                <pre className="text-xs text-[color:var(--text-primary)] bg-[color:var(--bg-primary)] border border-[color:var(--border)] rounded-lg p-3 whitespace-pre-wrap font-mono">{viewTask.payload}</pre>
              </div>

              {viewTask.result_summary && (
                <div>
                  <label className="block text-xs font-medium text-[color:var(--evo-green)] mb-1">Result</label>
                  <pre className="text-xs text-[color:var(--text-primary)] bg-[color:var(--bg-primary)] border border-[color:var(--border)] rounded-lg p-3 whitespace-pre-wrap font-mono max-h-64 overflow-y-auto">{viewTask.result_summary}</pre>
                </div>
              )}

              {viewTask.error && (
                <div>
                  <label className="block text-xs font-medium text-red-400 mb-1">Error</label>
                  <pre className="text-xs text-red-300 bg-red-500/5 border border-red-500/20 rounded-lg p-3 whitespace-pre-wrap font-mono max-h-48 overflow-y-auto">{viewTask.error}</pre>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
