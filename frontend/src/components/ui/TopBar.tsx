import { useState } from 'react'
import { useCanvasStore } from '@/store/canvasStore'
import { buildWorkflowSchema } from '@/lib/schemaBuilder'
import { Play, Save, Download, Sparkles, Loader2, Square, Library, FilePlus } from 'lucide-react'
import { toast } from 'sonner'
import { LibraryModal } from '@/components/drawers/LibraryModal'

export function TopBar() {
  const {
    workflowId, workflowName, nodes, edges,
    activeRunId, runStatus, recursionLimit,
    setWorkflow, setActiveRun, resetRunState,
    toggleCopilot, bumpWorkflows, newCanvas, setRecursionLimit,
  } = useCanvasStore()
  const [saving, setSaving]   = useState(false)
  const [running, setRunning] = useState(false)
  const [libraryOpen, setLibraryOpen] = useState(false)

  const handleSave = async () => {
    if (nodes.length === 0) {
      toast.error('Canvas is empty — add nodes before saving.')
      return
    }
    // Nudge users to name their workflow instead of saving it as "Untitled Workflow".
    let name = workflowName.trim()
    if (!name || name === 'Untitled Workflow') {
      const entered = window.prompt('Name this workflow:', name === 'Untitled Workflow' ? '' : name)
      if (entered === null) return
      name = entered.trim() || 'Untitled Workflow'
      setWorkflow(workflowId ?? 0, name)
    }
    setSaving(true)
    try {
      const schema: Record<string, unknown> = buildWorkflowSchema(nodes, edges, name, recursionLimit)
      if (workflowId) schema['workflow_id'] = workflowId

      const res = await fetch('/api/workflows/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, workflow_schema: schema }),
      })
      if (!res.ok) throw new Error('Save failed')
      const data = await res.json()
      setWorkflow(data.id, data.name)
      bumpWorkflows()
      toast.success('Workflow saved!')
    } catch (err) {
      toast.error('Failed to save workflow.')
    } finally {
      setSaving(false)
    }
  }

  const handleRun = async () => {
    if (!workflowId) {
      toast.error('Save the workflow before running it.')
      return
    }
    // Most workflows read initial_input.message, so collect a prompt up front
    // instead of starting with empty input (which silently produces no result).
    const message = window.prompt('Enter the input message for this run:', '')
    if (message === null) return
    setRunning(true)
    try {
      const res = await fetch('/api/runs/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ workflow_id: workflowId, initial_input: { message } }),
      })
      if (!res.ok) throw new Error('Run failed to start')
      const data = await res.json()
      setActiveRun(data.run_id)
      toast.success(`Run started: ${data.run_id.slice(0, 8)}`)
    } catch (err) {
      toast.error('Failed to start run.')
    } finally {
      setRunning(false)
    }
  }

  const handleStop = async () => {
    if (!activeRunId) return
    try {
      await fetch(`/api/runs/${activeRunId}/cancel`, { method: 'POST' })
      resetRunState()
      toast.info('Run cancelled.')
    } catch {
      toast.error('Failed to cancel run.')
    }
  }

  const handleExport = async () => {
    if (!workflowId) {
      toast.error('Save the workflow before exporting.')
      return
    }
    try {
      const res  = await fetch(`/api/workflows/${workflowId}/export`)
      if (!res.ok) throw new Error('Export failed')
      const code = await res.text()
      const blob = new Blob([code], { type: 'text/plain' })
      const url  = URL.createObjectURL(blob)
      const a    = document.createElement('a')
      a.href     = url
      a.download = `${workflowName.replace(/\s+/g, '_').toLowerCase()}.py`
      a.click()
      URL.revokeObjectURL(url)
      toast.success('Workflow exported as Python script!')
    } catch {
      toast.error('Export failed.')
    }
  }

  const handleNew = () => {
    if (nodes.length > 0 && !window.confirm('Start a new workflow? Unsaved changes will be lost.')) return
    newCanvas()
    toast.info('New blank canvas.')
  }

  const isRunActive = runStatus === 'running' || runStatus === 'paused'

  return (
    <>
    {libraryOpen && <LibraryModal onClose={() => setLibraryOpen(false)} />}
    <div className="h-12 bg-gray-900 border-b border-gray-700 flex items-center px-4 gap-3 flex-shrink-0">
      {/* Workflow name */}
      <input
        id="workflow-name-input"
        value={workflowName}
        onChange={(e) => setWorkflow(workflowId ?? 0, e.target.value)}
        className="bg-transparent text-white text-sm font-semibold focus:outline-none border-b border-transparent focus:border-indigo-500 px-1 w-48 truncate"
        placeholder="Workflow name..."
      />

      {/* Recursion limit (max node steps before LangGraph aborts the run) */}
      <div className="flex items-center gap-1.5 text-xs text-gray-400" title="Max node steps before the run aborts (LangGraph recursion limit).">
        <span className="uppercase tracking-wider text-[10px]">Max steps</span>
        <input
          id="recursion-limit-input"
          type="number"
          min={1}
          max={500}
          value={recursionLimit}
          onChange={(e) => setRecursionLimit(Math.max(1, Math.min(500, Number(e.target.value) || 50)))}
          className="w-16 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white text-xs focus:outline-none focus:border-indigo-500"
        />
      </div>

      <div className="flex-1" />

      {/* Run status badge */}
      {runStatus !== 'idle' && (
        <span className={`text-xs px-2 py-1 rounded-full font-medium ${
          runStatus === 'running'   ? 'bg-yellow-900/50 text-yellow-300' :
          runStatus === 'paused'    ? 'bg-indigo-900/50 text-indigo-300' :
          runStatus === 'completed' ? 'bg-green-900/50  text-green-300'  :
                                      'bg-red-900/50    text-red-300'
        }`}>
          {runStatus.toUpperCase()}
          {runStatus === 'paused' && ' ⏸ Waiting for input'}
        </span>
      )}

      {/* New canvas */}
      <button
        id="new-canvas-btn"
        onClick={handleNew}
        className="flex items-center gap-1.5 text-xs text-gray-200 hover:text-white bg-gray-800 hover:bg-gray-700 border border-gray-600 px-3 py-1.5 rounded-lg transition-colors cursor-pointer"
      >
        <FilePlus size={13} />
        New
      </button>

      {/* Library */}
      <button
        id="library-btn"
        onClick={() => setLibraryOpen(true)}
        className="flex items-center gap-1.5 text-xs text-gray-200 hover:text-white bg-gray-800 hover:bg-gray-700 border border-gray-600 px-3 py-1.5 rounded-lg transition-colors cursor-pointer"
      >
        <Library size={13} />
        Library
      </button>

      {/* Copilot toggle */}
      <button
        id="copilot-toggle-btn"
        onClick={toggleCopilot}
        className="flex items-center gap-1.5 text-xs text-purple-300 hover:text-purple-200 bg-purple-900/30 hover:bg-purple-900/50 border border-purple-800 px-3 py-1.5 rounded-lg transition-colors cursor-pointer"
      >
        <Sparkles size={13} />
        Copilot
      </button>

      {/* Save */}
      <button
        id="save-workflow-btn"
        onClick={handleSave}
        disabled={saving}
        className="flex items-center gap-1.5 text-xs text-gray-200 hover:text-white bg-gray-800 hover:bg-gray-700 border border-gray-600 px-3 py-1.5 rounded-lg transition-colors disabled:opacity-50 cursor-pointer"
      >
        {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
        Save
      </button>

      {/* Export */}
      <button
        id="export-workflow-btn"
        onClick={handleExport}
        className="flex items-center gap-1.5 text-xs text-gray-200 hover:text-white bg-gray-800 hover:bg-gray-700 border border-gray-600 px-3 py-1.5 rounded-lg transition-colors cursor-pointer"
      >
        <Download size={13} />
        Export
      </button>

      {/* Run / Stop */}
      {isRunActive ? (
        <button
          id="stop-run-btn"
          onClick={handleStop}
          className="flex items-center gap-1.5 text-xs text-red-200 bg-red-900/40 hover:bg-red-900/60 border border-red-800 px-3 py-1.5 rounded-lg transition-colors cursor-pointer"
        >
          <Square size={13} />
          Stop
        </button>
      ) : (
        <button
          id="run-workflow-btn"
          onClick={handleRun}
          disabled={running || !workflowId}
          className="flex items-center gap-1.5 text-xs text-green-200 bg-green-900/40 hover:bg-green-900/60 border border-green-800 px-3 py-1.5 rounded-lg transition-colors disabled:opacity-50 cursor-pointer"
        >
          {running
            ? <Loader2 size={13} className="animate-spin" />
            : <Play    size={13} />
          }
          Run
        </button>
      )}
    </div>
    </>
  )
}
