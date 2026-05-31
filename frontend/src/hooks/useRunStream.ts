import { useEffect, useRef } from 'react'
import { useCanvasStore } from '@/store/canvasStore'

export function useRunStream(runId: string | null) {
  const esRef = useRef<EventSource | null>(null)
  const lastEventIdRef = useRef<number>(0)

  useEffect(() => {
    if (!runId) return

    const connect = () => {
      const url = `/api/runs/${runId}/stream?last_event_id=${lastEventIdRef.current}`
      const es = new EventSource(url)
      esRef.current = es

      const remember = (e: MessageEvent) => {
        if (e.lastEventId) lastEventIdRef.current = parseInt(e.lastEventId, 10)
      }

      // Node execution state changes (running → completed → failed)
      es.addEventListener('node_state', (e) => {
        remember(e)
        const data = JSON.parse(e.data)
        const nodeId = data.node_id as string
        const status = data.status as 'running' | 'completed' | 'failed' | 'paused'
        useCanvasStore.getState().updateNodeState(nodeId, {
          status,
          output:  data.output as Record<string, unknown> | undefined,
        })
        const level = status === 'failed' ? 'error' : status === 'completed' ? 'success' : 'info'
        useCanvasStore.getState().appendLog(level, `Node "${nodeId}" ${status}`)
      })

      // Real-time token/cost updates
      es.addEventListener('cost_update', (e) => {
        remember(e)
        const data = JSON.parse(e.data)
        useCanvasStore.getState().updateNodeState(data.node_id as string, {
          tokensUsed:        data.total_tokens      as number,
          estimatedCostUsd:  data.estimated_cost_usd as number,
        })
        useCanvasStore.getState().appendLog(
          'info',
          `Node "${data.node_id}" used ${data.total_tokens} tokens ($${(data.estimated_cost_usd ?? 0).toFixed(4)})`,
        )
      })

      // Tool calls made by agents (web_search, code_interpreter, etc.)
      es.addEventListener('tool_call', (e) => {
        remember(e)
        const data = JSON.parse(e.data)
        const where = data.node_id ? `${data.node_id} → ` : ''
        if (data.phase === 'start') {
          useCanvasStore.getState().appendLog('info', `🔧 ${where}${data.tool}(${data.input ?? ''})`)
        } else {
          useCanvasStore.getState().appendLog('info', `🔧 ${data.tool} returned: ${data.output ?? ''}`)
        }
      })

      // run_paused handler — update runStatus so UI shows HITL waiting state
      es.addEventListener('run_paused', (e) => {
        remember(e)
        const data = JSON.parse(e.data)
        useCanvasStore.setState({ runStatus: 'paused' })
        // Mark the paused node specifically
        if (data.next_node) {
          useCanvasStore.getState().updateNodeState(data.next_node as string, { status: 'paused' })
        }
        useCanvasStore.getState().appendLog('warn', 'Run paused — waiting for human approval')
      })

      es.addEventListener('run_complete', (e) => {
        remember(e)
        const data = JSON.parse(e.data)
        useCanvasStore.setState({ runStatus: 'completed' })
        if (data.final_text) useCanvasStore.getState().setFinalOutput(data.final_text as string)
        useCanvasStore.getState().appendLog('success', 'Run completed')
        es.close()
      })

      es.addEventListener('run_failed', (e) => {
        remember(e)
        const data = JSON.parse(e.data)
        useCanvasStore.setState({ runStatus: 'failed' })
        console.error('Run failed:', data.error)
        useCanvasStore.getState().appendLog('error', `Run failed: ${data.error ?? 'unknown error'}`)
        es.close()
      })

      // run_cancelled handler
      es.addEventListener('run_cancelled', () => {
        useCanvasStore.setState({ runStatus: 'idle' })
        useCanvasStore.getState().appendLog('warn', 'Run cancelled')
        es.close()
      })

      // Heartbeat — connection alive, no action needed
      es.addEventListener('heartbeat', () => {})

      es.onerror = () => {
        es.close()
        // Auto-reconnect after 3 seconds with last seen event ID for replay
        setTimeout(connect, 3000)
      }
    }

    connect()
    return () => esRef.current?.close()
  }, [runId])
}
