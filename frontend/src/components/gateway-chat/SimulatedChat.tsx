import { useState, useRef, useEffect } from 'react'
import clsx from 'clsx'
import { useCanvasStore, type LogEntry } from '@/store/canvasStore'
import { Send, MessageCircle, Bot, Loader2, CheckCircle2, ChevronDown } from 'lucide-react'

interface ChatMessage {
  id: string
  role: 'user' | 'bot' | 'steps'
  content: string
  timestamp: Date
  runId?: string
  steps?: LogEntry[]   // frozen run-log snapshot once the run finishes
}

// Collapsible "execution steps" panel. While the run is active it binds live to
// the store's runLog; once frozen it renders the captured snapshot.
function StepsPanel({ runId, frozen }: { runId: string; frozen?: LogEntry[] }) {
  const liveLog     = useCanvasStore((s) => s.runLog)
  const activeRunId = useCanvasStore((s) => s.activeRunId)
  const runStatus   = useCanvasStore((s) => s.runStatus)
  const [open, setOpen] = useState(true)

  const isLive  = !frozen && runId === activeRunId
  const entries = frozen ?? (isLive ? liveLog : [])
  const running = isLive && runStatus === 'running'

  return (
    <div className="bg-gray-800/60 border border-gray-700 rounded-xl text-xs w-full">
      <button onClick={() => setOpen((o) => !o)} className="w-full flex items-center gap-2 px-3 py-2 text-left">
        {running
          ? <Loader2 size={13} className="animate-spin text-indigo-400 flex-shrink-0" />
          : <CheckCircle2 size={13} className="text-green-400 flex-shrink-0" />}
        <span className="font-medium text-gray-200">{running ? 'Working…' : 'Execution steps'}</span>
        <span className="text-gray-500">({entries.length})</span>
        <ChevronDown size={13} className={clsx('ml-auto transition-transform text-gray-400', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="px-3 pb-2 space-y-1 max-h-[260px] overflow-y-auto font-mono">
          {entries.length === 0 ? (
            <div className="text-gray-600 italic">No steps yet…</div>
          ) : (
            entries.map((e) => (
              <div key={e.id} className="flex gap-2 leading-relaxed">
                <span className="text-gray-600 flex-shrink-0">{e.time}</span>
                <span className={clsx(
                  'whitespace-pre-wrap break-words',
                  e.level === 'error'   && 'text-red-400',
                  e.level === 'success' && 'text-green-400',
                  e.level === 'warn'    && 'text-yellow-400',
                  e.level === 'info'    && 'text-gray-300',
                )}>{e.message}</span>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}

export function SimulatedChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([{
    id: '0',
    role: 'bot',
    content: '👋 Simulated Telegram Gateway. Type a message to trigger the active workflow.',
    timestamp: new Date(),
  }])
  const [input, setInput]     = useState('')
  const [sending, setSending] = useState(false)
  const { workflowId, activeRunId, runStatus, finalOutput, setActiveRun } = useCanvasStore()
  const bottomRef = useRef<HTMLDivElement>(null)

  const addBot = (content: string, runId?: string) =>
    setMessages((m) => [...m, {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      role: 'bot', content, timestamp: new Date(), runId,
    }])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Switching to a different workflow clears the chat so stale messages from the
  // previous workflow don't bleed into the new one.
  const lastFinalRef = useRef<string | null>(null)
  const lastStatusRef = useRef(runStatus)
  useEffect(() => {
    setMessages([{
      id: '0',
      role: 'bot',
      content: '👋 Simulated Telegram Gateway. Type a message to trigger the active workflow.',
      timestamp: new Date(),
    }])
    lastFinalRef.current = null
    lastStatusRef.current = runStatus
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowId])

  // Surface the final workflow output back into the chat as the bot's reply.
  useEffect(() => {
    if (finalOutput && finalOutput !== lastFinalRef.current) {
      lastFinalRef.current = finalOutput
      addBot(finalOutput)
    }
  }, [finalOutput])

  // Announce run status transitions and freeze the steps panel once the run ends.
  useEffect(() => {
    if (runStatus !== lastStatusRef.current) {
      lastStatusRef.current = runStatus
      if (runStatus === 'paused') addBot('⏸ Waiting for your input — reply below to continue.')
      if (runStatus === 'failed') addBot('❌ Run failed — expand the steps above to see what happened.')
      if (runStatus === 'completed' || runStatus === 'failed') {
        const { runLog, activeRunId: rid } = useCanvasStore.getState()
        const snapshot = [...runLog]
        setMessages((m) => m.map((msg) =>
          msg.role === 'steps' && msg.runId === rid && !msg.steps
            ? { ...msg, steps: snapshot }
            : msg,
        ))
      }
    }
  }, [runStatus])

  const sendMessage = async () => {
    if (!input.trim() || !workflowId) return
    setSending(true)

    const sentInput = input
    setMessages((m) => [...m, {
      id: Date.now().toString(),
      role: 'user', content: sentInput, timestamp: new Date(),
    }])
    setInput('')

    try {
      // A paused run is waiting on a human reply — resume it instead of starting anew.
      if (runStatus === 'paused' && activeRunId) {
        const res = await fetch(`/api/runs/${activeRunId}/resume`, {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ value: sentInput }),
        })
        if (!res.ok) throw new Error('resume failed')
        useCanvasStore.setState({ runStatus: 'running' })
        addBot('↩️ Reply sent — resuming the workflow...')
      } else {
        const res = await fetch('/api/gateway/simulate', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ workflow_id: workflowId, message: sentInput }),
        })
        if (!res.ok) throw new Error('start failed')
        const data = await res.json()
        setActiveRun(data.run_id)
        // Insert a live steps panel; the final answer arrives as a separate bubble.
        setMessages((m) => [...m, {
          id: `steps-${data.run_id}`,
          role: 'steps', content: '', timestamp: new Date(), runId: data.run_id,
        }])
      }
    } catch {
      addBot('❌ Failed to reach the workflow. Check that a workflow is saved and active.')
    } finally {
      setSending(false)
    }
  }

  const placeholder = !workflowId
    ? 'Save a workflow first...'
    : runStatus === 'paused'
      ? 'Reply to continue the paused run...'
      : 'Type a message...'

  return (
    <div id="simulated-chat" className="flex flex-col h-full bg-gray-900 border-l border-gray-700">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-700">
        <MessageCircle size={16} className="text-blue-400" />
        <span className="text-sm font-semibold text-white">Simulated Gateway</span>
        <span className="text-xs bg-blue-900/50 text-blue-300 px-2 py-0.5 rounded-full ml-auto">
          Local Only
        </span>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.map((msg) =>
          msg.role === 'steps' && msg.runId ? (
            <StepsPanel key={msg.id} runId={msg.runId} frozen={msg.steps} />
          ) : (
            <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              {msg.role === 'bot' && (
                <div className="w-7 h-7 rounded-full bg-blue-600 flex items-center justify-center mr-2 flex-shrink-0">
                  <Bot size={14} className="text-white" />
                </div>
              )}
              <div className={`max-w-[80%] px-3 py-2 rounded-xl text-sm ${
                msg.role === 'user'
                  ? 'bg-indigo-600 text-white rounded-br-sm'
                  : 'bg-gray-800 text-gray-100 rounded-bl-sm'
              }`}>
                <pre className="whitespace-pre-wrap font-sans text-xs">{msg.content}</pre>
                <div className="text-[10px] opacity-50 mt-1">{msg.timestamp.toLocaleTimeString()}</div>
              </div>
            </div>
          ),
        )}
        <div ref={bottomRef} />
      </div>

      <div className="flex items-center gap-2 px-4 py-3 border-t border-gray-700">
        <input
          id="chat-input"
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && !sending && sendMessage()}
          placeholder={placeholder}
          disabled={!workflowId}
          className="flex-1 bg-gray-800 text-white placeholder-gray-500 text-sm px-3 py-2 rounded-lg border border-gray-700 focus:outline-none focus:border-indigo-500 disabled:opacity-50"
        />
        <button
          id="send-chat-btn"
          onClick={sendMessage}
          disabled={sending || !workflowId}
          className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white p-2 rounded-lg transition-colors cursor-pointer"
        >
          <Send size={16} />
        </button>
      </div>
    </div>
  )
}
