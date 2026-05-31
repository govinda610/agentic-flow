import type { Edge } from '@xyflow/react'
import { useCanvasStore } from '@/store/canvasStore'
import { X, Trash2 } from 'lucide-react'

type EdgeType = 'normal' | 'conditional' | 'error'

const TYPES: { key: EdgeType; label: string; hint: string }[] = [
  { key: 'normal',      label: 'Normal',      hint: 'Always follows this edge.' },
  { key: 'conditional', label: 'Conditional', hint: 'Follows only when the expression is true.' },
  { key: 'error',       label: 'On error',    hint: 'Followed when the source node fails.' },
]

export function EdgeInspector({ edgeId, onClose }: { edgeId: string; onClose: () => void }) {
  const { edges, setEdges } = useCanvasStore()
  const edge = edges.find((e) => e.id === edgeId)
  if (!edge) return null

  const edgeType = (edge.data?.edgeType as EdgeType) ?? 'normal'
  const condition = (edge.data?.condition as string | null) ?? ''
  const label = (edge.label as string) ?? ''

  const patch = (next: Partial<{ edgeType: EdgeType; condition: string | null; label: string }>) => {
    setEdges(edges.map((e) => {
      if (e.id !== edgeId) return e
      const data = { ...(e.data ?? {}) }
      if (next.edgeType !== undefined)  data.edgeType = next.edgeType
      if (next.condition !== undefined) data.condition = next.condition
      return {
        ...e,
        data,
        label: next.label !== undefined ? next.label : e.label,
        animated: (next.edgeType ?? edgeType) === 'normal',
        className: (next.edgeType ?? edgeType) === 'error' ? 'edge-error' : '',
      } as Edge
    }))
  }

  const remove = () => { setEdges(edges.filter((e) => e.id !== edgeId)); onClose() }

  return (
    <div className="absolute top-4 left-1/2 -translate-x-1/2 z-40 w-[360px] bg-gray-900 border border-gray-700 rounded-xl shadow-2xl text-white">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-700">
        <span className="text-sm font-semibold">Edge: {edge.source} → {edge.target}</span>
        <button onClick={onClose} className="text-gray-400 hover:text-white"><X size={15} /></button>
      </div>

      <div className="p-4 space-y-3">
        <div>
          <label className="text-xs text-gray-400 uppercase tracking-wider">Type</label>
          <div className="flex gap-1.5 mt-1">
            {TYPES.map((t) => (
              <button
                key={t.key}
                onClick={() => patch({ edgeType: t.key })}
                className={`flex-1 py-1.5 text-xs rounded-lg border transition-colors ${
                  edgeType === t.key
                    ? 'bg-indigo-600 border-indigo-500 text-white'
                    : 'bg-gray-800 border-gray-700 text-gray-300 hover:bg-gray-700'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
          <p className="text-[11px] text-gray-500 mt-1">{TYPES.find((t) => t.key === edgeType)?.hint}</p>
        </div>

        {edgeType === 'conditional' && (
          <div>
            <label className="text-xs text-gray-400 uppercase tracking-wider">Condition expression</label>
            <textarea
              value={condition}
              onChange={(e) => patch({ condition: e.target.value })}
              rows={3}
              placeholder="state['node_outputs']['node_verifier']['is_approved'] == True"
              className="w-full bg-gray-800 text-white px-3 py-2 mt-1 rounded-lg border border-gray-700 focus:border-indigo-500 focus:outline-none text-xs font-mono resize-none"
            />
            <p className="text-[11px] text-gray-500 mt-1">
              Evaluated against <code>state</code>. Safe subset only — no imports or calls.
            </p>
          </div>
        )}

        <div>
          <label className="text-xs text-gray-400 uppercase tracking-wider">Label</label>
          <input
            value={label}
            onChange={(e) => patch({ label: e.target.value })}
            placeholder="optional label shown on the edge"
            className="w-full bg-gray-800 text-white px-3 py-2 mt-1 rounded-lg border border-gray-700 focus:border-indigo-500 focus:outline-none text-sm"
          />
        </div>

        <button
          onClick={remove}
          className="flex items-center gap-1.5 text-xs text-red-300 hover:text-red-200 bg-red-900/30 hover:bg-red-900/50 border border-red-800 px-3 py-1.5 rounded-lg transition-colors"
        >
          <Trash2 size={13} /> Delete edge
        </button>
      </div>
    </div>
  )
}
