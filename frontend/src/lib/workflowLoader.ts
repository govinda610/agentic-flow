import type { Node, Edge } from '@xyflow/react'

// Inverse of buildWorkflowSchema: turn a stored workflow schema (nodes/edges with
// a nested `config`) back into ReactFlow nodes/edges for the canvas.

interface SchemaNode {
  id: string
  type: string
  position?: { x: number; y: number }
  config?: Record<string, unknown>
}

interface SchemaEdge {
  id: string
  source: string
  target: string
  type?: string
  condition?: string | null
  label?: string
  fan_out_from?: string | null
}

export interface WorkflowSchema {
  name?: string
  recursion_limit?: number
  nodes?: SchemaNode[]
  edges?: SchemaEdge[]
}

export function schemaToFlow(schema: WorkflowSchema): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = (schema.nodes ?? []).map((n, i) => {
    const config = n.config ?? {}
    return {
      id: n.id,
      type: n.type,
      position: n.position ?? { x: 120 + i * 220, y: 160 },
      data: {
        type: n.type,
        label: (config.name as string) || (config.label as string) || n.type,
        config,
        // Mirror config fields to the top level so NodeConfigPanel initializes from them.
        system_prompt: config.system_prompt ?? '',
        tools: config.tools ?? [],
        skills: config.skills ?? [],
        mcp_servers: config.mcp_servers ?? [],
        structured_output: config.structured_output ?? null,
        max_depth: config.max_depth ?? 1,
        max_breadth: config.max_breadth ?? 2,
      },
    }
  })

  const edges: Edge[] = (schema.edges ?? []).map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    label: e.label || undefined,
    data: {
      edgeType: e.type ?? 'normal',
      condition: e.condition ?? null,
      fan_out_from: e.fan_out_from ?? null,
    },
  }))

  return { nodes, edges }
}
