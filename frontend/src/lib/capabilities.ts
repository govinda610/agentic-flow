// Typed client for the capability library API (/api/capabilities).
// A capability is a reusable tool, skill, or MCP server the user defines once
// and references by name from any workflow node.

export type CapabilityKind = 'tool' | 'skill' | 'mcp'

export interface Capability {
  id: number
  name: string
  kind: CapabilityKind
  description: string | null
  config: Record<string, unknown>
}

export interface CapabilityInput {
  name: string
  kind: CapabilityKind
  description?: string | null
  config: Record<string, unknown>
}

export async function listCapabilities(kind?: CapabilityKind): Promise<Capability[]> {
  const url = kind ? `/api/capabilities/?kind=${kind}` : '/api/capabilities/'
  const res = await fetch(url)
  if (!res.ok) throw new Error('Failed to load capabilities')
  return res.json()
}

export interface BuiltinTool {
  name: string
  description: string
}

export async function listBuiltinTools(): Promise<BuiltinTool[]> {
  const res = await fetch('/api/capabilities/builtins')
  if (!res.ok) throw new Error('Failed to load built-in tools')
  return res.json()
}

export async function createCapability(data: CapabilityInput): Promise<Capability> {
  const res = await fetch('/api/capabilities/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Create failed')
  return res.json()
}

export async function updateCapability(id: number, data: CapabilityInput): Promise<Capability> {
  const res = await fetch(`/api/capabilities/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Update failed')
  return res.json()
}

export async function deleteCapability(id: number): Promise<void> {
  const res = await fetch(`/api/capabilities/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('Delete failed')
}
