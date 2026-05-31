import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { Play, Square } from 'lucide-react'

export const StartNode = memo((_: NodeProps) => (
  <div className="px-4 py-2 rounded-full bg-green-600 border-2 border-green-400 text-white flex items-center gap-2">
    <Play size={14} />
    <span className="text-sm font-bold">Start</span>
    <Handle type="source" position={Position.Right} className="!bg-green-400" />
  </div>
))
StartNode.displayName = 'StartNode'

export const EndNode = memo((_: NodeProps) => (
  <div className="px-4 py-2 rounded-full bg-red-700 border-2 border-red-500 text-white flex items-center gap-2">
    <Handle type="target" position={Position.Left} className="!bg-red-400" />
    <Square size={14} />
    <span className="text-sm font-bold">End</span>
  </div>
))
EndNode.displayName = 'EndNode'
