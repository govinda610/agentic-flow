import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useCanvasStore } from '@/store/canvasStore'
import { autoLayout } from '@/lib/autoLayout'
import { buildWorkflowSchema } from '@/lib/schemaBuilder'
import { Sparkles, Send, Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import type { Node, Edge } from '@xyflow/react'

interface CopilotMessage {
  role: 'user' | 'assistant'
  content: string
}

async function generateWorkflow(
  prompt: string,
  context: Record<string, unknown> = {},
): Promise<{ workflow_schema: Record<string, unknown>; message: string }> {
  const res = await fetch('/api/generate-workflow', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, context }),
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(body || `HTTP ${res.status}`)
  }
  return res.json()
}

export function CopilotPanel() {
  const [input, setInput] = useState('')
  const [history, setHistory] = useState<CopilotMessage[]>([{
    role: 'assistant',
    content: "✨ I'm your Design-Time Copilot. Describe a workflow in plain English and I'll build it for you — or, with a workflow already on the canvas, ask me to edit it.\n\nCreate: \"A researcher agent that feeds into a summary writer, then notify me via Telegram.\"\nEdit: \"Add a fact-checker between the researcher and the writer.\"",
  }])
  const { setNodes, setEdges, setWorkflow, bumpWorkflows, setRecursionLimit } = useCanvasStore()

  const mutation = useMutation({
    mutationFn: (vars: { prompt: string; context: Record<string, unknown> }) =>
      generateWorkflow(vars.prompt, vars.context),
    onSuccess: async (data: { workflow_schema: Record<string, unknown>; message: string }) => {
      const schema = data.workflow_schema as { nodes: unknown[]; edges: unknown[]; name?: string; workflow_id?: unknown; recursion_limit?: number }

      const rawNodes: Node[] = (schema.nodes as Array<Record<string, unknown>>).map((n: Record<string, unknown>) => ({
        id:   n.id as string,
        type: n.type as string,
        position: (n.position as { x: number; y: number }) ?? { x: 0, y: 0 },
        data: {
          label: (n.config as Record<string, unknown>)?.name ?? n.id,
          type:  n.type,
          config: n.config ?? {},
        },
      }))

      const rawEdges: Edge[] = (schema.edges as Array<Record<string, unknown>>).map((e: Record<string, unknown>) => ({
        id:     e.id as string,
        source: e.source as string,
        target: e.target as string,
        label:  (e.label as string | null | undefined) ?? '',
        data: {
          edgeType:    e.type,
          condition:   e.condition,
          fan_out_from: e.fan_out_from ?? null,
        },
        className: (e.type as string) === 'error' ? 'edge-error' : '',
        animated:  (e.type as string) === 'normal',
      }))

      // Apply topological auto-layout before rendering
      const layoutedNodes = autoLayout(rawNodes, rawEdges)

      setNodes(layoutedNodes)
      setEdges(rawEdges)
      const recursionLimit = typeof schema.recursion_limit === 'number' ? schema.recursion_limit : 50
      setRecursionLimit(recursionLimit)

      // Auto-save so the workflow is immediately runnable (no manual Save step).
      const name = schema.name ? String(schema.name) : 'Copilot Workflow'
      try {
        const built = buildWorkflowSchema(layoutedNodes, rawEdges, name, recursionLimit)
        const res = await fetch('/api/workflows/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, workflow_schema: built }),
        })
        if (!res.ok) throw new Error('save failed')
        const saved = await res.json()
        setWorkflow(saved.id, saved.name)
        bumpWorkflows()
        setHistory((h) => [...h, {
          role: 'assistant',
          content: `✅ ${data.message}\n\nWorkflow rendered and **saved** — hit Run (or send a message in the gateway) to execute it.`,
        }])
        toast.success('Workflow generated and saved!')
      } catch {
        if (schema.name) setWorkflow(0, name)
        setHistory((h) => [...h, {
          role: 'assistant',
          content: `✅ ${data.message}\n\nWorkflow rendered on canvas. Auto-save failed — click **Save** to persist it.`,
        }])
        toast.success('Workflow generated (save manually).')
      }
    },
    onError: (err: Error) => {
      setHistory((h) => [...h, {
        role: 'assistant' as const,
        content: `❌ Generation failed: ${err.message}. Try rephrasing your request.`,
      }])
      toast.error('Copilot generation failed.')
    },
  })

  const handleSend = () => {
    if (!input.trim() || mutation.isPending) return
    setHistory((h) => [...h, { role: 'user', content: input }])
    // If the canvas already has a workflow, send it as context so the Copilot
    // edits it instead of starting from scratch.
    const { nodes, edges, workflowName, recursionLimit } = useCanvasStore.getState()
    const context = nodes.length > 0
      ? buildWorkflowSchema(nodes, edges, workflowName, recursionLimit)
      : {}
    mutation.mutate({ prompt: input, context })
    setInput('')
  }

  return (
    <div id="copilot-panel" className="flex flex-col h-full bg-gray-900 border-l border-gray-700">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-700">
        <Sparkles size={16} className="text-purple-400" />
        <span className="text-sm font-semibold text-white">Design Copilot</span>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {history.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[90%] px-3 py-2 rounded-xl text-sm ${
              msg.role === 'user'
                ? 'bg-purple-700 text-white rounded-br-sm'
                : 'bg-gray-800 text-gray-100 rounded-bl-sm'
            }`}>
              <pre className="whitespace-pre-wrap font-sans text-xs">{msg.content}</pre>
            </div>
          </div>
        ))}
        {mutation.isPending && (
          <div className="flex items-center gap-2 text-gray-400 text-sm">
            <Loader2 size={14} className="animate-spin" />
            Generating workflow...
          </div>
        )}
      </div>

      <div className="flex gap-2 px-4 py-3 border-t border-gray-700">
        <textarea
          id="copilot-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              handleSend()
            }
          }}
          placeholder="Describe your workflow..."
          rows={2}
          className="flex-1 bg-gray-800 text-white placeholder-gray-500 text-sm px-3 py-2 rounded-lg border border-gray-700 focus:outline-none focus:border-purple-500 resize-none"
        />
        <button
          id="copilot-send-btn"
          onClick={handleSend}
          disabled={mutation.isPending}
          className="bg-purple-600 hover:bg-purple-500 disabled:opacity-40 text-white p-2 rounded-lg transition-colors self-end cursor-pointer"
        >
          <Send size={16} />
        </button>
      </div>
    </div>
  )
}
