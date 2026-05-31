import React, { useState, useEffect, useCallback } from 'react'
import { FolderOpen, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { useCanvasStore } from '@/store/canvasStore'
import { schemaToFlow, type WorkflowSchema } from '@/lib/workflowLoader'

interface WorkflowMeta {
  id: number
  name: string
  template_slug: string | null
  is_template: boolean
}

function WorkflowRow({
  wf, accent, onOpen, onDelete, onDragStart,
}: {
  wf: WorkflowMeta
  accent: string
  onOpen: (wf: WorkflowMeta) => void
  onDelete?: (wf: WorkflowMeta) => void
  onDragStart: (e: React.DragEvent, nodeType: string, name: string, wfId?: number, wfSlug?: string | null) => void
}) {
  return (
    <div
      draggable
      onDragStart={(e) => onDragStart(e, 'subgraph', wf.name, wf.id, wf.template_slug)}
      className={`group flex items-center justify-between gap-2 ${accent} px-3 py-2 rounded-lg text-sm cursor-grab active:cursor-grabbing font-medium`}
    >
      <span className="truncate">{wf.name}</span>
      <div className="flex items-center gap-1 flex-shrink-0">
        <button
          title="Open on canvas"
          onClick={(e) => { e.stopPropagation(); onOpen(wf) }}
          className="text-gray-400 hover:text-white opacity-60 group-hover:opacity-100 cursor-pointer"
        >
          <FolderOpen size={14} />
        </button>
        {onDelete && (
          <button
            title="Delete workflow"
            onClick={(e) => { e.stopPropagation(); onDelete(wf) }}
            className="text-gray-400 hover:text-red-400 opacity-60 group-hover:opacity-100 cursor-pointer"
          >
            <Trash2 size={14} />
          </button>
        )}
      </div>
    </div>
  )
}

export function NodePalette() {
  const [savedWorkflows, setSavedWorkflows] = useState<WorkflowMeta[]>([])
  const { setNodes, setEdges, setWorkflow, resetRunState, workflowsVersion, setRecursionLimit, newCanvas, workflowId } = useCanvasStore()

  const reload = useCallback(() => {
    fetch('/api/workflows')
      .then((res) => res.json())
      .then((data: WorkflowMeta[]) => setSavedWorkflows(data))
      .catch((err) => console.error('Failed to load workflows', err))
  }, [])

  // Re-fetch on mount and whenever a save bumps workflowsVersion.
  useEffect(() => { reload() }, [reload, workflowsVersion])

  const openOnCanvas = useCallback(async (wf: WorkflowMeta) => {
    try {
      const res = await fetch(`/api/workflows/${wf.id}`)
      if (!res.ok) throw new Error('not found')
      const data = await res.json()
      const schema = data.workflow_schema as WorkflowSchema
      const { nodes, edges } = schemaToFlow(schema)
      resetRunState()
      setNodes(nodes)
      setEdges(edges)
      setRecursionLimit(schema.recursion_limit ?? 50)
      setWorkflow(wf.id, schema.name || wf.name)
      toast.success(`Opened "${wf.name}" on the canvas.`)
    } catch {
      toast.error('Failed to open workflow.')
    }
  }, [setNodes, setEdges, setWorkflow, resetRunState, setRecursionLimit])

  const deleteWorkflow = useCallback(async (wf: WorkflowMeta) => {
    if (!window.confirm(`Delete workflow "${wf.name}"? This cannot be undone.`)) return
    try {
      const res = await fetch(`/api/workflows/${wf.id}`, { method: 'DELETE' })
      if (!res.ok) throw new Error('delete failed')
      // If the deleted workflow is open on the canvas, clear it.
      if (workflowId === wf.id) newCanvas()
      setSavedWorkflows((list) => list.filter((w) => w.id !== wf.id))
      toast.success(`Deleted "${wf.name}".`)
    } catch {
      toast.error('Failed to delete workflow.')
    }
  }, [workflowId, newCanvas])

  const onDragStart = (
    event: React.DragEvent,
    nodeType: string,
    name: string,
    wfId?: number,
    wfSlug?: string | null,
  ) => {
    event.dataTransfer.setData('application/reactflow', nodeType)
    event.dataTransfer.setData('application/reactflow-name', name)
    if (wfId) {
      event.dataTransfer.setData('application/reactflow-wf-id', wfId.toString())
    }
    if (wfSlug) {
      event.dataTransfer.setData('application/reactflow-wf-slug', wfSlug)
    }
    event.dataTransfer.effectAllowed = 'move'
  }

  const templates = savedWorkflows.filter((w) => w.is_template)
  const myWorkflows = savedWorkflows.filter((w) => !w.is_template)

  return (
    <div className="w-[240px] bg-gray-900 border-r border-gray-800 p-4 flex flex-col gap-4 text-white overflow-y-auto font-sans">
      <div>
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Flow Control</h3>
        <p className="text-[10px] text-gray-600 mb-2">Every workflow needs a Start and an End node. Select a node and press Delete to remove it.</p>
        <div className="flex flex-col gap-2">
          <div
            draggable
            onDragStart={(e) => onDragStart(e, 'start', 'Start')}
            className="bg-green-950/40 hover:bg-green-900/40 border border-green-800 px-3 py-2 rounded-lg text-sm cursor-grab active:cursor-grabbing font-medium"
          >
            Start
          </div>
          <div
            draggable
            onDragStart={(e) => onDragStart(e, 'end', 'End')}
            className="bg-red-950/40 hover:bg-red-900/40 border border-red-800 px-3 py-2 rounded-lg text-sm cursor-grab active:cursor-grabbing font-medium"
          >
            End
          </div>
        </div>
      </div>

      <div>
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Standard Nodes</h3>
        <div className="flex flex-col gap-2">
          {(['simple_llm', 'agent', 'deep_agent', 'supervisor', 'human_chat', 'telegram_output', 'webhook_trigger'] as const).map((type) => (
            <div
              key={type}
              draggable
              onDragStart={(e) => onDragStart(e, type, type.replace(/_/g, ' ').toUpperCase())}
              className="bg-gray-800 hover:bg-gray-700 border border-gray-700 px-3 py-2 rounded-lg text-sm cursor-grab active:cursor-grabbing font-medium capitalize"
            >
              {type.replace(/_/g, ' ')}
            </div>
          ))}
        </div>
      </div>

      {templates.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Templates</h3>
          <p className="text-[10px] text-gray-600 mb-2">Click the folder icon to open on the canvas.</p>
          <div className="flex flex-col gap-2">
            {templates.map((wf) => (
              <WorkflowRow key={wf.id} wf={wf} onOpen={openOnCanvas} onDragStart={onDragStart} accent="bg-emerald-950/40 hover:bg-emerald-900/40 border border-emerald-800" />
            ))}
          </div>
        </div>
      )}

      <div>
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">My Workflows</h3>
        <p className="text-[10px] text-gray-600 mb-2">Open on canvas, or drag to embed as a sub-graph.</p>
        <div className="flex flex-col gap-2">
          {myWorkflows.length === 0 && <div className="text-xs text-gray-600 italic">No saved workflows yet.</div>}
          {myWorkflows.map((wf) => (
            <WorkflowRow key={wf.id} wf={wf} onOpen={openOnCanvas} onDelete={deleteWorkflow} onDragStart={onDragStart} accent="bg-indigo-950/40 hover:bg-indigo-900/40 border border-indigo-800" />
          ))}
        </div>
      </div>
    </div>
  )
}
