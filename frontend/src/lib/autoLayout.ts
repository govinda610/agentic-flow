import dagre from '@dagrejs/dagre'
import type { Node, Edge } from '@xyflow/react'

/**
 * Auto-layout using @dagrejs/dagre (Left-to-Right orientation).
 * Handles DAGs and cyclical feedback loops.
 */
export function autoLayout(nodes: Node[], edges: Edge[]): Node[] {
  if (nodes.length === 0) return nodes

  const g = new dagre.graphlib.Graph()
  g.setGraph({ rankdir: 'LR', nodesep: 80, ranksep: 120 })
  g.setDefaultEdgeLabel(() => ({}))

  nodes.forEach((node) => {
    g.setNode(node.id, { width: 180, height: 80 })
  })

  edges.forEach((edge) => {
    g.setEdge(edge.source, edge.target)
  })

  dagre.layout(g)

  return nodes.map((node) => {
    const pos = g.node(node.id)
    return {
      ...node,
      position: {
        x: pos.x - 90, // centre on node width
        y: pos.y - 40, // centre on node height
      },
    }
  })
}
