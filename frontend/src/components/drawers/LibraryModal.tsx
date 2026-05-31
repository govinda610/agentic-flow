import { useCallback, useEffect, useState } from 'react'
import { X, Plus, Trash2, Save, Pencil } from 'lucide-react'
import { toast } from 'sonner'
import {
  listCapabilities, createCapability, updateCapability, deleteCapability,
  listBuiltinTools,
  type Capability, type CapabilityKind, type BuiltinTool,
} from '@/lib/capabilities'

const KINDS: { key: CapabilityKind; label: string }[] = [
  { key: 'tool',  label: 'Tools' },
  { key: 'skill', label: 'Skills' },
  { key: 'mcp',   label: 'MCP Servers' },
]

// Per-kind editor metadata: which config field holds the body, and how it is shaped.
const CONFIG_FIELD: Record<CapabilityKind, { field: string; label: string; placeholder: string; json: boolean }> = {
  tool:  { field: 'code',    label: 'Python tool code (@tool decorated function)', placeholder: 'from langchain.tools import tool\n\n@tool\ndef my_tool(x: str) -> str:\n    """Describe what it does."""\n    return x', json: false },
  skill: { field: 'content', label: 'SKILL.md content', placeholder: '---\nname: my_skill\ndescription: what it teaches\n---\n\nInstructions...', json: false },
  mcp:   { field: 'servers', label: 'Servers map (JSON)', placeholder: '{\n  "my_server": {\n    "command": "npx",\n    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],\n    "transport": "stdio"\n  }\n}', json: true },
}

interface DraftState {
  id: number | null
  name: string
  description: string
  body: string
}

export function LibraryModal({ onClose }: { onClose: () => void }) {
  const [kind, setKind]   = useState<CapabilityKind>('tool')
  const [items, setItems] = useState<Capability[]>([])
  const [builtins, setBuiltins] = useState<BuiltinTool[]>([])
  const [draft, setDraft] = useState<DraftState | null>(null)
  const [saving, setSaving] = useState(false)

  const meta = CONFIG_FIELD[kind]

  const reload = useCallback(() => {
    listCapabilities(kind).then(setItems).catch(() => toast.error('Failed to load library.'))
  }, [kind])

  useEffect(() => { reload() }, [reload])
  useEffect(() => { listBuiltinTools().then(setBuiltins).catch(() => {}) }, [])

  const selectKind = (k: CapabilityKind) => { setKind(k); setDraft(null) }
  const startNew  = () => setDraft({ id: null, name: '', description: '', body: '' })
  const startEdit = (c: Capability) => setDraft({
    id: c.id,
    name: c.name,
    description: c.description ?? '',
    body: meta.json
      ? JSON.stringify((c.config[meta.field] as unknown) ?? {}, null, 2)
      : String(c.config[meta.field] ?? ''),
  })

  const save = async () => {
    if (!draft) return
    if (!draft.name.trim()) { toast.error('Name is required.'); return }

    let config: Record<string, unknown>
    if (meta.json) {
      try {
        config = { [meta.field]: JSON.parse(draft.body || '{}') }
      } catch {
        toast.error('Servers map must be valid JSON.')
        return
      }
    } else {
      config = { [meta.field]: draft.body }
    }

    setSaving(true)
    try {
      const payload = { name: draft.name.trim(), kind, description: draft.description || null, config }
      if (draft.id === null) await createCapability(payload)
      else await updateCapability(draft.id, payload)
      toast.success('Capability saved.')
      setDraft(null)
      reload()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Save failed.')
    } finally {
      setSaving(false)
    }
  }

  const remove = async (c: Capability) => {
    try {
      await deleteCapability(c.id)
      toast.info(`Deleted ${c.name}.`)
      if (draft?.id === c.id) setDraft(null)
      reload()
    } catch {
      toast.error('Delete failed.')
    }
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="w-[760px] max-h-[80vh] bg-gray-900 border border-gray-700 rounded-xl shadow-2xl flex flex-col text-white"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-700">
          <span className="font-semibold text-sm">Capability Library</span>
          <button onClick={onClose} className="text-gray-400 hover:text-white"><X size={16} /></button>
        </div>

        {/* Kind tabs */}
        <div className="flex border-b border-gray-700">
          {KINDS.map((k) => (
            <button
              key={k.key}
              onClick={() => selectKind(k.key)}
              className={`flex-1 py-2 text-[11px] font-bold uppercase tracking-wider border-b-2 transition-colors ${
                kind === k.key ? 'text-indigo-400 border-indigo-400' : 'text-gray-500 border-transparent hover:text-gray-300'
              }`}
            >
              {k.label}
            </button>
          ))}
        </div>

        <div className="flex flex-1 overflow-hidden">
          {/* List */}
          <div className="w-1/2 border-r border-gray-700 flex flex-col">
            <div className="flex items-center justify-between px-3 py-2">
              <span className="text-xs text-gray-400 uppercase">{items.length} saved</span>
              <button onClick={startNew} className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1">
                <Plus size={12} /> New
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-3 pb-3 space-y-2">
              {kind === 'tool' && builtins.length > 0 && (
                <div className="space-y-2">
                  <div className="text-[10px] text-gray-500 uppercase tracking-wider">Built-in (always available)</div>
                  {builtins.map((b) => (
                    <div key={b.name} className="bg-gray-800/40 rounded-lg p-2.5 border border-gray-800">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium text-gray-200 truncate">{b.name}</span>
                        <span className="text-[9px] text-gray-500 uppercase flex-shrink-0">built-in</span>
                      </div>
                      {b.description && <div className="text-xs text-gray-500 mt-1 line-clamp-2">{b.description}</div>}
                    </div>
                  ))}
                  <div className="text-[10px] text-gray-500 uppercase tracking-wider pt-1">Your tools</div>
                </div>
              )}
              {items.length === 0 && <div className="text-xs text-gray-600 italic">Nothing here yet.</div>}
              {items.map((c) => (
                <div key={c.id} className="bg-gray-800 rounded-lg p-2.5 border border-gray-700">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium truncate">{c.name}</span>
                    <div className="flex gap-2 flex-shrink-0">
                      <button onClick={() => startEdit(c)} className="text-gray-400 hover:text-indigo-300"><Pencil size={13} /></button>
                      <button onClick={() => remove(c)} className="text-gray-400 hover:text-red-400"><Trash2 size={13} /></button>
                    </div>
                  </div>
                  {c.description && <div className="text-xs text-gray-500 mt-1 line-clamp-2">{c.description}</div>}
                </div>
              ))}
            </div>
          </div>

          {/* Editor */}
          <div className="w-1/2 flex flex-col overflow-y-auto p-3 space-y-3">
            {!draft ? (
              <div className="text-xs text-gray-600 italic m-auto">Select an item to edit, or click New.</div>
            ) : (
              <>
                <div>
                  <label className="text-xs text-gray-400 uppercase mb-1 block">Name</label>
                  <input
                    value={draft.name}
                    onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                    placeholder="unique_name"
                    className="w-full bg-gray-800 text-white px-3 py-2 rounded-lg border border-gray-700 focus:border-indigo-500 focus:outline-none text-sm"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-400 uppercase mb-1 block">Description</label>
                  <input
                    value={draft.description}
                    onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                    placeholder="what it does"
                    className="w-full bg-gray-800 text-white px-3 py-2 rounded-lg border border-gray-700 focus:border-indigo-500 focus:outline-none text-sm"
                  />
                </div>
                <div className="flex-1 flex flex-col">
                  <label className="text-xs text-gray-400 uppercase mb-1 block">{meta.label}</label>
                  <textarea
                    value={draft.body}
                    onChange={(e) => setDraft({ ...draft, body: e.target.value })}
                    placeholder={meta.placeholder}
                    rows={10}
                    className="w-full flex-1 bg-gray-800 text-white px-3 py-2 rounded-lg border border-gray-700 focus:border-indigo-500 focus:outline-none text-xs font-mono resize-none"
                  />
                </div>
                <button
                  onClick={save}
                  disabled={saving}
                  className="bg-indigo-600 hover:bg-indigo-500 text-white py-2 rounded-lg text-sm font-medium flex items-center justify-center gap-2 disabled:opacity-50"
                >
                  <Save size={14} /> {draft.id === null ? 'Create' : 'Update'}
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
