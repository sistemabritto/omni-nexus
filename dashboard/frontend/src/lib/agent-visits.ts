const RECENT_KEY = 'evo:recent-agents'
const MAX_RECENT = 6
export function trackAgentVisit(agentName: string) {
  try {
    const raw = localStorage.getItem(RECENT_KEY)
    let data: { name: string; ts: number }[] = raw ? JSON.parse(raw) : []
    data = data.filter(d => d.name !== agentName)
    data.unshift({ name: agentName, ts: Date.now() })
    data = data.slice(0, MAX_RECENT)
    localStorage.setItem(RECENT_KEY, JSON.stringify(data))
  } catch { /* Storage unavailable: navigation still works. */ }
}
