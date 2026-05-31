import { create } from 'zustand'
import type { Node, Edge } from '@xyflow/react'

export type NodeStatus = 'idle' | 'running' | 'completed' | 'failed' | 'paused'

export interface NodeState {
  status: NodeStatus
  output?: Record<string, unknown>
  tokensUsed?: number
  estimatedCostUsd?: number
  error?: string
}

export type LogLevel = 'info' | 'success' | 'error' | 'warn'

export interface LogEntry {
  id: number
  time: string
  level: LogLevel
  message: string
}

const MAX_LOG_ENTRIES = 200

interface CanvasStore {
  // Workflow
  workflowId: number | null
  workflowName: string
  nodes: Node[]
  edges: Edge[]
  recursionLimit: number

  // Run
  activeRunId: string | null
  runStatus: 'idle' | 'running' | 'paused' | 'completed' | 'failed'
  nodeStates: Record<string, NodeState>
  runLog: LogEntry[]
  finalOutput: string | null

  // UI
  selectedNodeId: string | null
  isDrawerOpen: boolean
  drawerTab: 'io' | 'logs' | 'costs' | 'inbox'
  isCopilotOpen: boolean

  // Bumped whenever the saved-workflow list changes so the palette can re-fetch.
  workflowsVersion: number

  // Actions
  setNodes: (nodes: Node[]) => void
  setEdges: (edges: Edge[]) => void
  setWorkflow: (id: number, name: string) => void
  setActiveRun: (runId: string) => void
  appendLog: (level: LogLevel, message: string) => void
  setFinalOutput: (text: string | null) => void
  updateNodeState: (nodeId: string, state: Partial<NodeState>) => void
  setSelectedNode: (nodeId: string | null) => void
  toggleDrawer: (open?: boolean) => void
  setDrawerTab: (tab: 'io' | 'logs' | 'costs' | 'inbox') => void
  toggleCopilot: () => void
  resetRunState: () => void
  bumpWorkflows: () => void
  newCanvas: () => void
  setRecursionLimit: (limit: number) => void
}

export const useCanvasStore = create<CanvasStore>((set) => ({
  workflowId: null,
  workflowName: 'Untitled Workflow',
  nodes: [],
  edges: [],
  recursionLimit: 50,
  activeRunId: null,
  runStatus: 'idle',
  nodeStates: {},
  runLog: [],
  finalOutput: null,
  selectedNodeId: null,
  isDrawerOpen: false,
  drawerTab: 'io',
  isCopilotOpen: false,
  workflowsVersion: 0,

  setNodes:    (nodes) => set({ nodes }),
  setEdges:    (edges) => set({ edges }),
  setWorkflow: (id, name) => set({ workflowId: id, workflowName: name }),
  setActiveRun:(runId) => set({ activeRunId: runId, runStatus: 'running', nodeStates: {}, runLog: [], finalOutput: null }),

  appendLog: (level, message) => set((s) => {
    const entry: LogEntry = {
      id: (s.runLog[s.runLog.length - 1]?.id ?? 0) + 1,
      time: new Date().toLocaleTimeString(),
      level,
      message,
    }
    const next = [...s.runLog, entry]
    return { runLog: next.length > MAX_LOG_ENTRIES ? next.slice(-MAX_LOG_ENTRIES) : next }
  }),

  setFinalOutput: (text) => set({ finalOutput: text }),

  updateNodeState: (nodeId, state) => set((s) => ({
    nodeStates: {
      ...s.nodeStates,
      [nodeId]: { ...s.nodeStates[nodeId], ...state },
    },
  })),

  setSelectedNode: (nodeId) => set({ selectedNodeId: nodeId, isDrawerOpen: nodeId !== null }),
  toggleDrawer:    (open)   => set((s) => ({ isDrawerOpen: open ?? !s.isDrawerOpen })),
  setDrawerTab:    (tab)    => set({ drawerTab: tab }),
  toggleCopilot:   ()       => set((s) => ({ isCopilotOpen: !s.isCopilotOpen })),
  resetRunState:   ()       => set({ activeRunId: null, runStatus: 'idle', nodeStates: {}, runLog: [], finalOutput: null }),
  bumpWorkflows:   ()       => set((s) => ({ workflowsVersion: s.workflowsVersion + 1 })),
  setRecursionLimit: (limit) => set({ recursionLimit: limit }),
  newCanvas:       ()       => set({
    workflowId: null,
    workflowName: 'Untitled Workflow',
    nodes: [],
    edges: [],
    recursionLimit: 50,
    selectedNodeId: null,
    isDrawerOpen: false,
    activeRunId: null,
    runStatus: 'idle',
    nodeStates: {},
    runLog: [],
    finalOutput: null,
  }),
}))
