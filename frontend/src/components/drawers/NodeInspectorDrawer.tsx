import { useEffect, useState } from 'react'
import type { Node } from '@xyflow/react'
import { useCanvasStore } from '@/store/canvasStore'
import { X, ChevronRight } from 'lucide-react'
import clsx from 'clsx'
import { NodeConfigPanel } from '@/components/canvas/NodeConfigPanel'

interface NodeIOData {
  node_id: string
  status: string
  input_state_json: string | null
  output_state_json: string | null
  tokens_used: number
  estimated_cost_usd: number
}

interface InboxMessage {
  id: number
  from_node_id: string
  to_node_id: string
  message_content: string
  is_read: boolean
  created_at: string
  read_at: string | null
}

export function NodeInspectorDrawer() {
  const {
    selectedNodeId, isDrawerOpen, drawerTab, activeRunId,
    nodes, runLog, setSelectedNode, setDrawerTab, setNodes,
  } = useCanvasStore()

  const [nodeData, setNodeData]         = useState<NodeIOData | null>(null)
  const [inboxMessages, setInboxMessages] = useState<InboxMessage[]>([])
  const [loading, setLoading]           = useState(false)

  const selectedNode = nodes.find((n: Node) => n.id === selectedNodeId)
  const isStartNode  = selectedNode?.type === 'start'

  useEffect(() => {
    if (!selectedNodeId || !activeRunId || !isDrawerOpen) return
    setLoading(true)
    fetch(`/api/runs/${activeRunId}/steps/${selectedNodeId}`)
      .then((r) => r.json())
      .then(setNodeData)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [selectedNodeId, activeRunId, isDrawerOpen])

  useEffect(() => {
    if (drawerTab === 'inbox' && selectedNodeId && activeRunId && isDrawerOpen) {
      fetch(`/api/runs/${activeRunId}/inbox/${selectedNodeId}`)
        .then((r) => r.json())
        .then(setInboxMessages)
        .catch(console.error)
    }
  }, [selectedNodeId, activeRunId, drawerTab, isDrawerOpen])

  if (!isDrawerOpen || !selectedNode) return null

  const updateNodeConfig = (key: string, value: any) => {
    setNodes(nodes.map((n: Node) => {
      if (n.id !== selectedNodeId) return n
      const nextConfig = { ...((n.data.config as Record<string, any>) || {}), [key]: value }
      return { ...n, data: { ...n.data, config: nextConfig, ...nextConfig } }
    }))
  }

  const nodeConfig = (selectedNode.data.config as Record<string, any>) || {}

  return (
    <div
      id="node-inspector-drawer"
      className="fixed right-0 top-0 h-full w-[440px] bg-gray-900 border-l border-gray-700 z-50 flex flex-col shadow-2xl text-white"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
        <div className="flex items-center gap-2">
          <ChevronRight size={16} className="text-indigo-400" />
          <span className="font-semibold text-sm">
            {activeRunId
              ? `Inspect: ${selectedNode.data.label}`
              : `Configure: ${selectedNode.data.label}`}
          </span>
        </div>
        <button
          id="close-drawer-btn"
          onClick={() => setSelectedNode(null)}
          className="text-gray-400 hover:text-white"
        >
          <X size={16} />
        </button>
      </div>

      {/* Tabs (only shown during an active run) */}
      {activeRunId && (
        <div className="flex border-b border-gray-700 bg-gray-900/50">
          {(['io', 'logs', 'costs', 'inbox'] as const).map((tab) => (
            <button
              key={tab}
              id={`drawer-tab-${tab}`}
              onClick={() => setDrawerTab(tab)}
              className={clsx(
                'flex-1 py-2 text-[10px] font-bold uppercase tracking-wider transition-colors border-b-2',
                drawerTab === tab
                  ? 'text-indigo-400 border-indigo-400'
                  : 'text-gray-500 border-transparent hover:text-gray-300',
              )}
            >
              {tab}
            </button>
          ))}
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        {activeRunId ? (
          <>
            {loading && <div className="text-gray-500 text-sm">Loading...</div>}

            {!loading && drawerTab === 'io' && nodeData && (
              <div className="space-y-4">
                <div>
                  <div className="text-xs text-gray-400 uppercase mb-2">Input State</div>
                  <pre className="bg-gray-800 rounded-lg p-3 text-xs text-green-300 overflow-auto max-h-[200px] whitespace-pre-wrap">
                    {nodeData.input_state_json
                      ? JSON.stringify(JSON.parse(nodeData.input_state_json), null, 2)
                      : 'No input recorded'}
                  </pre>
                </div>
                <div>
                  <div className="text-xs text-gray-400 uppercase mb-2">Output State</div>
                  <pre className="bg-gray-800 rounded-lg p-3 text-xs text-blue-300 overflow-auto max-h-[200px] whitespace-pre-wrap">
                    {nodeData.output_state_json
                      ? JSON.stringify(JSON.parse(nodeData.output_state_json), null, 2)
                      : 'No output recorded'}
                  </pre>
                </div>
              </div>
            )}

            {drawerTab === 'logs' && (
              <div className="space-y-1 font-mono text-xs">
                {runLog.length === 0 ? (
                  <div className="text-gray-500 italic">No log entries yet.</div>
                ) : (
                  runLog.map((entry) => (
                    <div key={entry.id} className="flex gap-2 leading-relaxed">
                      <span className="text-gray-600 flex-shrink-0">{entry.time}</span>
                      <span
                        className={clsx(
                          'whitespace-pre-wrap break-words',
                          entry.level === 'error'   && 'text-red-400',
                          entry.level === 'success' && 'text-green-400',
                          entry.level === 'warn'    && 'text-yellow-400',
                          entry.level === 'info'    && 'text-gray-300',
                        )}
                      >
                        {entry.message}
                      </span>
                    </div>
                  ))
                )}
              </div>
            )}

            {!loading && drawerTab === 'costs' && nodeData && (
              <div className="space-y-2">
                <div className="bg-gray-800 rounded-lg p-3">
                  <div className="text-xs text-gray-400">Tokens Used</div>
                  <div className="text-2xl font-bold">{nodeData.tokens_used?.toLocaleString() ?? 0}</div>
                </div>
                <div className="bg-gray-800 rounded-lg p-3">
                  <div className="text-xs text-gray-400">Estimated Cost</div>
                  <div className="text-2xl font-bold text-green-400">
                    ${nodeData.estimated_cost_usd?.toFixed(4) ?? '0.0000'}
                  </div>
                </div>
              </div>
            )}

            {!loading && drawerTab === 'inbox' && (
              <div className="space-y-3">
                <div className="text-xs text-gray-400 uppercase mb-2">Inter-Agent Inbox Messages</div>
                {inboxMessages.length === 0 ? (
                  <div className="text-gray-500 text-xs italic">No messages in inbox.</div>
                ) : (
                  inboxMessages.map((msg) => (
                    <div key={msg.id} className="bg-gray-800 rounded-lg p-3 text-xs border border-gray-700">
                      <div className="flex justify-between text-gray-400 mb-1">
                        <span>From: <strong className="text-indigo-400">{msg.from_node_id}</strong></span>
                        <span>{new Date(msg.created_at).toLocaleTimeString()}</span>
                      </div>
                      <div className="text-white whitespace-pre-wrap">{msg.message_content}</div>
                    </div>
                  ))
                )}
              </div>
            )}
          </>
        ) : (
          /* Configuration panel (design-time) */
          <div className="space-y-4">
            {isStartNode && (
              <div className="space-y-3">
                <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Workflow Triggers</h3>
                <div>
                  <label className="text-xs text-gray-400">Cron Schedule (Proactive Execution)</label>
                  <input
                    type="text"
                    value={nodeConfig.cron_schedule || ''}
                    onChange={(e) => updateNodeConfig('cron_schedule', e.target.value)}
                    placeholder="e.g. */30 * * * * for every 30 minutes"
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 mt-1 text-sm focus:outline-none focus:border-indigo-500 text-white"
                  />
                </div>
                <div className="flex items-center justify-between bg-gray-800/40 p-3 rounded-lg border border-gray-800">
                  <div>
                    <label className="text-sm font-medium">Enable Telegram Gateway</label>
                    <div className="text-xs text-gray-400">Direct conversational chat</div>
                  </div>
                  <input
                    type="checkbox"
                    checked={nodeConfig.enable_telegram || false}
                    onChange={(e) => updateNodeConfig('enable_telegram', e.target.checked)}
                    className="w-4 h-4 text-indigo-600 border-gray-700 rounded focus:ring-indigo-500"
                  />
                </div>
              </div>
            )}

            {!isStartNode && selectedNode.type !== 'end' && (
              <NodeConfigPanel key={selectedNodeId} />
            )}
          </div>
        )}
      </div>

      <div className="p-4 border-t border-gray-700 bg-gray-900/50 flex justify-end">
        <button
          onClick={() => setSelectedNode(null)}
          className="bg-indigo-600 hover:bg-indigo-500 text-white text-xs px-4 py-2 rounded-lg font-medium transition-colors cursor-pointer"
        >
          {activeRunId ? 'Close' : 'Apply Settings'}
        </button>
      </div>
    </div>
  )
}
