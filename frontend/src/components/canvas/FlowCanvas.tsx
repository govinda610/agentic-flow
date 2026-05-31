import React, { useCallback, useState } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useReactFlow,
  addEdge,
  applyNodeChanges,
  applyEdgeChanges,
  BackgroundVariant,
  type Connection,
  type NodeChange,
  type EdgeChange,
  type Edge,
} from '@xyflow/react'
import { useCanvasStore } from '@/store/canvasStore'
import { AgentNode } from './nodes/AgentNode'
import { StartNode, EndNode } from './nodes/StartEndNode'
import { EdgeInspector } from './EdgeInspector'
import { useRunStream } from '@/hooks/useRunStream'

// nodeTypes must be defined outside the component to avoid recreation on each render
const nodeTypes = {
  agent:        AgentNode,
  simple_llm:   AgentNode,
  deep_agent:   AgentNode,
  supervisor:   AgentNode,
  human_chat:   AgentNode,
  subgraph:     AgentNode,
  telegram_output: AgentNode,
  webhook_trigger: AgentNode,
  start:        StartNode,
  end:          EndNode,
}

export function FlowCanvas() {
  const { nodes: storeNodes, edges: storeEdges, activeRunId, setNodes, setEdges } = useCanvasStore()
  const reactFlow = useReactFlow()
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null)

  useRunStream(activeRunId)

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => setNodes(applyNodeChanges(changes, storeNodes)),
    [setNodes, storeNodes],
  )

  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => setEdges(applyEdgeChanges(changes, storeEdges)),
    [setEdges, storeEdges],
  )

  const onConnect = useCallback(
    (params: Connection) => setEdges(addEdge(
      { ...params, data: { edgeType: 'normal', condition: null }, animated: true },
      storeEdges,
    )),
    [setEdges, storeEdges],
  )

  const onEdgeClick = useCallback(
    (_: React.MouseEvent, edge: Edge) => setSelectedEdgeId(edge.id),
    [],
  )

  const onDrop = useCallback((event: React.DragEvent) => {
    event.preventDefault()
    const nodeType = event.dataTransfer.getData('application/reactflow')
    if (!nodeType) return

    const nodeName   = event.dataTransfer.getData('application/reactflow-name')
    const wfIdStr    = event.dataTransfer.getData('application/reactflow-wf-id')
    const wfSlug     = event.dataTransfer.getData('application/reactflow-wf-slug')
    const position   = reactFlow.screenToFlowPosition({ x: event.clientX, y: event.clientY })

    // FIX: include subgraph config (workflow_id) for sub-workflow nodes
    const newNode = {
      id:       `node_${crypto.randomUUID()}`,
      type:     nodeType,
      position,
      data: {
        type:   nodeType,
        label:  nodeName || nodeType,
        config: nodeType === 'subgraph' && wfIdStr
          ? { workflow_id: parseInt(wfIdStr, 10), name: nodeName }
          : { system_prompt: '', tools: [], structured_output: null },
        ...(wfSlug ? { template_slug: wfSlug } : {}),
      },
    }
    setNodes([...storeNodes, newNode])
  }, [reactFlow, setNodes, storeNodes])

  return (
    <div className="w-full h-full bg-gray-950">
      <ReactFlow
        id="flow-canvas"
        nodes={storeNodes}
        edges={storeEdges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onEdgeClick={onEdgeClick}
        onPaneClick={() => setSelectedEdgeId(null)}
        onDrop={onDrop}
        onDragOver={(e) => e.preventDefault()}
        deleteKeyCode={['Backspace', 'Delete']}
        fitView
        snapToGrid={true}
        snapGrid={[20, 20]}
        proOptions={{ hideAttribution: true }}
        colorMode="dark"
      >
        <Background variant={BackgroundVariant.Dots} color="#374151" gap={24} />
        <Controls className="!bg-gray-800 !border-gray-700" />
        <MiniMap
          className="!bg-gray-900 !border-gray-700"
          nodeColor={(n) => {
            const status = useCanvasStore.getState().nodeStates[n.id]?.status
            if (status === 'running')   return '#fbbf24'
            if (status === 'completed') return '#22c55e'
            if (status === 'failed')    return '#ef4444'
            if (status === 'paused')    return '#6366f1'
            return '#374151'
          }}
        />
      </ReactFlow>
      {selectedEdgeId && (
        <EdgeInspector edgeId={selectedEdgeId} onClose={() => setSelectedEdgeId(null)} />
      )}
    </div>
  )
}
