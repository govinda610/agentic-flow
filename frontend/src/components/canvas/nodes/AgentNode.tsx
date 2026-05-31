import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { useCanvasStore } from '@/store/canvasStore'
import { Bot, Zap, BrainCircuit, Users, GitBranch } from 'lucide-react'
import clsx from 'clsx'

const NODE_ICONS: Record<string, React.ElementType> = {
  simple_llm:   Zap,
  agent:        Bot,
  deep_agent:   BrainCircuit,
  supervisor:   Users,
  cloned_agent: GitBranch,
}

const NODE_LABELS: Record<string, string> = {
  simple_llm:      'LLM Node',
  agent:           'Agent',
  deep_agent:      'Deep Agent',
  supervisor:      'Supervisor',
  cloned_agent:    'Clone Agent',
  start:           'Start',
  end:             'End',
  telegram_output: 'Telegram',
  webhook_trigger: 'Webhook',
  human_chat:      'Human Input',
}

export const AgentNode = memo(({ id, data, selected }: NodeProps) => {
  const nodeState    = useCanvasStore((s) => s.nodeStates[id])
  const setSelectedNode = useCanvasStore((s) => s.setSelectedNode)
  const status   = nodeState?.status ?? 'idle'
  const nodeType = (data.type as string) ?? 'agent'
  const Icon     = NODE_ICONS[nodeType] ?? Bot

  return (
    <div
      id={`node-${id}`}
      onClick={() => setSelectedNode(id)}
      className={clsx(
        'relative px-4 py-3 rounded-xl border-2 cursor-pointer transition-all duration-300',
        'bg-gray-900 text-white min-w-[160px]',
        {
          'node-running  border-yellow-400':                  status === 'running',
          'node-completed border-green-400':                  status === 'completed',
          'node-failed   border-red-400':                     status === 'failed',
          'node-paused   border-indigo-400':                  status === 'paused',
          'border-gray-600 hover:border-indigo-400':          status === 'idle',
          'border-indigo-500 ring-2 ring-indigo-400':         selected && status === 'idle',
        }
      )}
    >
      <Handle type="target" position={Position.Left}  className="!bg-gray-500 !border-gray-400" />

      <div className="flex items-center gap-2">
        <div className={clsx('p-1.5 rounded-lg', {
          'bg-yellow-900/50': status === 'running',
          'bg-green-900/50':  status === 'completed',
          'bg-red-900/50':    status === 'failed',
          'bg-indigo-900/50': status === 'idle' || status === 'paused',
        })}>
          <Icon size={14} className={clsx({
            'text-yellow-400': status === 'running',
            'text-green-400':  status === 'completed',
            'text-red-400':    status === 'failed',
            'text-indigo-400': status === 'idle' || status === 'paused',
          })} />
        </div>
        <div>
          <div className="text-xs text-gray-400 uppercase tracking-wider">
            {NODE_LABELS[nodeType] ?? nodeType}
          </div>
          <div className="text-sm font-semibold text-white truncate max-w-[120px]">
            {(data.label as string) || 'Unnamed'}
          </div>
        </div>
      </div>

      {status === 'running' && (
        <div className="absolute -top-1 -right-1 w-3 h-3 bg-yellow-400 rounded-full animate-ping" />
      )}
      {status === 'paused' && (
        <div className="absolute -top-1 -right-1 text-[9px] bg-indigo-500 text-white px-1 rounded">⏸</div>
      )}
      {nodeState?.tokensUsed != null && nodeState.tokensUsed > 0 && (
        <div className="text-xs text-gray-500 mt-1">
          {nodeState.tokensUsed.toLocaleString()} tokens
          {nodeState.estimatedCostUsd != null && ` · $${nodeState.estimatedCostUsd.toFixed(4)}`}
        </div>
      )}

      <Handle type="source" position={Position.Right} className="!bg-gray-500 !border-gray-400" />
    </div>
  )
})

AgentNode.displayName = 'AgentNode'
