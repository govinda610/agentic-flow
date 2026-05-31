import type { Node, Edge } from '@xyflow/react'

export function buildWorkflowSchema(
  nodes: Node[],
  edges: Edge[],
  workflowName: string,
  recursionLimit = 50,
) {
  return {
    name: workflowName,
    recursion_limit: recursionLimit,
    nodes: nodes.map((n) => ({
      id:       n.id,
      type:     (n.data?.type ?? n.type ?? 'agent') as string,
      position: n.position,
      // Prefer the nested config object; fall back to reading fields directly from data
      config: (n.data?.config as Record<string, unknown>) ?? {
        label:            n.data?.label            ?? '',
        name:             n.data?.name             ?? '',
        system_prompt:    n.data?.system_prompt    ?? '',
        tools:            n.data?.tools            ?? [],
        structured_output:n.data?.structured_output ?? null,
        max_depth:        n.data?.max_depth         ?? 1,
        max_breadth:      n.data?.max_breadth       ?? 2,
        middlewares:      n.data?.middlewares       ?? [],
      },
    })),
    edges: edges.map((e) => ({
      id:        e.id,
      source:    e.source,
      target:    e.target,
      type:      (e.data?.edgeType ?? 'normal') as string,
      condition: (e.data?.condition ?? null) as string | null,
      label:     (e.label ?? '') as string,
      fan_out_from: (e.data?.fan_out_from ?? null) as string | null,
    })),
  }
}
