import { useEffect, useState } from 'react'
import { useCanvasStore } from '@/store/canvasStore'
import { Plus, Trash2, Save } from 'lucide-react'
import { toast } from 'sonner'
import { listCapabilities, type Capability } from '@/lib/capabilities'

interface StructuredOutputField {
  name: string
  type: 'string' | 'boolean' | 'integer' | 'number' | 'array'
}

export function NodeConfigPanel() {
  const { selectedNodeId, nodes, setNodes } = useCanvasStore()
  const selectedNode = nodes.find((n) => n.id === selectedNodeId)

  const [systemPrompt, setSystemPrompt] = useState(
    (selectedNode?.data?.system_prompt as string | undefined) ?? ''
  )
  const [tools, setTools] = useState<string[]>(
    (selectedNode?.data?.tools as string[] | undefined) ?? []
  )
  const [skills, setSkills] = useState<string[]>(
    (selectedNode?.data?.skills as string[] | undefined) ?? []
  )
  const [mcpServers, setMcpServers] = useState<string[]>(
    (selectedNode?.data?.mcp_servers as string[] | undefined) ?? []
  )
  const [userTools, setUserTools] = useState<Capability[]>([])
  const [skillCaps, setSkillCaps] = useState<Capability[]>([])
  const [mcpCaps, setMcpCaps]     = useState<Capability[]>([])

  useEffect(() => {
    listCapabilities('tool').then(setUserTools).catch(() => {})
    listCapabilities('skill').then(setSkillCaps).catch(() => {})
    listCapabilities('mcp').then(setMcpCaps).catch(() => {})
  }, [])
  const [fields, setFields] = useState<StructuredOutputField[]>(
    (selectedNode?.data?.structured_output as { fields: StructuredOutputField[] } | null)?.fields ?? []
  )
  const [maxDepth, setMaxDepth] = useState<number>(
    (selectedNode?.data?.max_depth as number | undefined) ?? 1
  )
  const [maxBreadth, setMaxBreadth] = useState<number>(
    (selectedNode?.data?.max_breadth as number | undefined) ?? 2
  )

  if (!selectedNode || ['start', 'end'].includes(selectedNode.data?.type as string)) return null

  const addField    = () => setFields([...fields, { name: '', type: 'string' }])
  const removeField = (i: number) => setFields(fields.filter((_, idx) => idx !== i))
  const updateField = (i: number, key: keyof StructuredOutputField, value: string) => {
    setFields(fields.map((f, idx) => (idx === i ? { ...f, [key]: value } : f)))
  }

  const saveConfig = () => {
    const cleanedFields = fields
      .map((f) => ({ ...f, name: f.name.trim() }))
      .filter((f) => f.name.length > 0)

    const uniqueNames = new Set(cleanedFields.map((f) => f.name))
    if (uniqueNames.size !== cleanedFields.length) {
      toast.error('Structured output field names must be unique and non-empty.')
      return
    }

    setNodes(nodes.map((n) =>
      n.id !== selectedNodeId ? n : {
        ...n,
        data: {
          ...n.data,
          system_prompt:    systemPrompt,
          tools,
          skills,
          mcp_servers:      mcpServers,
          max_depth:        maxDepth,
          max_breadth:      maxBreadth,
          structured_output: cleanedFields.length > 0 ? { fields: cleanedFields } : null,
          // Keep config in sync for schemaBuilder
          config: {
            ...((n.data.config as Record<string, unknown>) ?? {}),
            system_prompt:    systemPrompt,
            tools,
            skills,
            mcp_servers:      mcpServers,
            max_depth:        maxDepth,
            max_breadth:      maxBreadth,
            structured_output: cleanedFields.length > 0 ? { fields: cleanedFields } : null,
          },
        },
      }
    ))
    toast.success('Node configuration saved.')
  }

  const nodeType = selectedNode.data?.type as string
  // For deep agents, we omit filesystem/todo/memory tools from selection because deep_agent handles them natively
  const BUILTIN_TOOLS = nodeType === 'deep_agent'
    ? ['code_interpreter', 'web_search', 'clone_agent', 'send_inbox_message', 'read_inbox_messages']
    : ['code_interpreter', 'web_search', 'file_reader', 'file_writer', 'write_todos', 'write_memory', 'clone_agent', 'send_inbox_message', 'read_inbox_messages']
  // User-defined Python tools from the capability library extend the built-in set.
  const AVAILABLE_TOOLS = [...BUILTIN_TOOLS, ...userTools.map((t) => t.name)]

  const toggleIn = (list: string[], set: (v: string[]) => void, value: string) =>
    set(list.includes(value) ? list.filter((x) => x !== value) : [...list, value])

  return (
    <div id="node-config-panel" className="space-y-4 text-sm">
      <div>
        <label className="text-xs text-gray-400 uppercase mb-1 block">System Prompt</label>
        <textarea
          id="node-system-prompt"
          value={systemPrompt}
          onChange={(e) => setSystemPrompt(e.target.value)}
          rows={5}
          className="w-full bg-gray-800 text-white px-3 py-2 rounded-lg border border-gray-700 focus:border-indigo-500 focus:outline-none text-sm resize-none"
        />
      </div>

      <div>
        <label className="text-xs text-gray-400 uppercase mb-2 block">Tools</label>
        <div className="flex flex-wrap gap-2">
          {AVAILABLE_TOOLS.map((t) => (
            <button
              key={t}
              id={`tool-toggle-${t}`}
              onClick={() => toggleIn(tools, setTools, t)}
              className={`px-2 py-1 rounded text-xs border transition-colors cursor-pointer ${
                tools.includes(t)
                  ? 'bg-indigo-700 border-indigo-500 text-white'
                  : 'bg-gray-800 border-gray-600 text-gray-400 hover:border-gray-400'
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {/* Skills — reusable SKILL.md capabilities from the library */}
      <div>
        <label className="text-xs text-gray-400 uppercase mb-2 block">Skills</label>
        {skillCaps.length === 0 ? (
          <div className="text-xs text-gray-600 italic">No skills in library — add some in the Library.</div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {skillCaps.map((s) => (
              <button
                key={s.name}
                id={`skill-toggle-${s.name}`}
                onClick={() => toggleIn(skills, setSkills, s.name)}
                className={`px-2 py-1 rounded text-xs border transition-colors cursor-pointer ${
                  skills.includes(s.name)
                    ? 'bg-emerald-700 border-emerald-500 text-white'
                    : 'bg-gray-800 border-gray-600 text-gray-400 hover:border-gray-400'
                }`}
              >
                {s.name}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* MCP servers — reusable MCP capabilities from the library */}
      <div>
        <label className="text-xs text-gray-400 uppercase mb-2 block">MCP Servers</label>
        {mcpCaps.length === 0 ? (
          <div className="text-xs text-gray-600 italic">No MCP servers in library — add some in the Library.</div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {mcpCaps.map((m) => (
              <button
                key={m.name}
                id={`mcp-toggle-${m.name}`}
                onClick={() => toggleIn(mcpServers, setMcpServers, m.name)}
                className={`px-2 py-1 rounded text-xs border transition-colors cursor-pointer ${
                  mcpServers.includes(m.name)
                    ? 'bg-amber-700 border-amber-500 text-white'
                    : 'bg-gray-800 border-gray-600 text-gray-400 hover:border-gray-400'
                }`}
              >
                {m.name}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Recursion limits — only for node types that can spawn children */}
      {['deep_agent', 'supervisor', 'agent'].includes(nodeType) && (
        <div className="flex gap-3">
          <div className="flex-1">
            <label className="text-xs text-gray-400 uppercase mb-1 block">Max Depth</label>
            <input
              id="node-max-depth"
              type="number"
              min={0}
              max={5}
              value={maxDepth}
              onChange={(e) => setMaxDepth(parseInt(e.target.value, 10))}
              className="w-full bg-gray-800 text-white px-3 py-2 rounded-lg border border-gray-700 focus:border-indigo-500 focus:outline-none text-sm"
            />
          </div>
          <div className="flex-1">
            <label className="text-xs text-gray-400 uppercase mb-1 block">Max Breadth</label>
            <input
              id="node-max-breadth"
              type="number"
              min={0}
              max={10}
              value={maxBreadth}
              onChange={(e) => setMaxBreadth(parseInt(e.target.value, 10))}
              className="w-full bg-gray-800 text-white px-3 py-2 rounded-lg border border-gray-700 focus:border-indigo-500 focus:outline-none text-sm"
            />
          </div>
        </div>
      )}

      {/* Structured Output Fields */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="text-xs text-gray-400 uppercase">Structured Output Fields</label>
          <button
            id="add-output-field-btn"
            onClick={addField}
            className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1 cursor-pointer"
          >
            <Plus size={12} /> Add Field
          </button>
        </div>
        {fields.map((field, i) => (
          <div key={i} className="flex gap-2 mb-2">
            <input
              id={`field-name-${i}`}
              value={field.name}
              onChange={(e) => updateField(i, 'name', e.target.value)}
              placeholder="field_name"
              className="flex-1 bg-gray-800 text-white px-2 py-1.5 rounded border border-gray-700 text-xs focus:outline-none"
            />
            <select
              id={`field-type-${i}`}
              value={field.type}
              onChange={(e) => updateField(i, 'type', e.target.value as StructuredOutputField['type'])}
              className="bg-gray-800 text-white px-2 py-1.5 rounded border border-gray-700 text-xs focus:outline-none"
            >
              {(['string', 'boolean', 'integer', 'number', 'array'] as const).map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
            <button
              onClick={() => removeField(i)}
              className="text-gray-500 hover:text-red-400 cursor-pointer"
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
        {fields.length === 0 && (
          <div className="text-xs text-gray-600 italic">No structured output (raw text response)</div>
        )}
      </div>

      <button
        id="save-node-config-btn"
        onClick={saveConfig}
        className="w-full bg-indigo-600 hover:bg-indigo-500 text-white py-2 rounded-lg text-sm font-medium flex items-center justify-center gap-2 transition-colors cursor-pointer"
      >
        <Save size={14} /> Save Node Config
      </button>
    </div>
  )
}
