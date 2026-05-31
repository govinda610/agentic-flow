import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReactFlowProvider } from '@xyflow/react'
import { FlowCanvas } from '@/components/canvas/FlowCanvas'
import { NodePalette } from '@/components/canvas/NodePalette'
import { NodeInspectorDrawer } from '@/components/drawers/NodeInspectorDrawer'
import { SimulatedChat } from '@/components/gateway-chat/SimulatedChat'
import { CopilotPanel } from '@/components/copilot/CopilotPanel'
import { Toaster } from 'sonner'
import { TopBar } from '@/components/ui/TopBar'
import { useCanvasStore } from '@/store/canvasStore'

const queryClient = new QueryClient()

function AppShell() {
  const isCopilotOpen = useCanvasStore((s) => s.isCopilotOpen)
  const setCopilot = (open: boolean) => useCanvasStore.setState({ isCopilotOpen: open })

  return (
    <div id="app-root" className="flex flex-col h-screen bg-gray-950 text-white font-sans overflow-hidden select-none">
      <TopBar />
      <div className="flex flex-1 overflow-hidden">
        {/* Left sidebar — node palette */}
        <NodePalette />

        {/* Main canvas */}
        <div className="flex-1 relative overflow-hidden">
          <FlowCanvas />
        </div>

        {/* Right panel — Gateway / Copilot, switchable via tabs */}
        <div className="w-[320px] border-l border-gray-700 flex-shrink-0 flex flex-col">
          <div className="flex border-b border-gray-700 flex-shrink-0">
            <button
              id="panel-tab-gateway"
              onClick={() => setCopilot(false)}
              className={`flex-1 py-2 text-[11px] font-bold uppercase tracking-wider border-b-2 transition-colors ${
                !isCopilotOpen ? 'text-blue-400 border-blue-400' : 'text-gray-500 border-transparent hover:text-gray-300'
              }`}
            >
              Gateway
            </button>
            <button
              id="panel-tab-copilot"
              onClick={() => setCopilot(true)}
              className={`flex-1 py-2 text-[11px] font-bold uppercase tracking-wider border-b-2 transition-colors ${
                isCopilotOpen ? 'text-purple-400 border-purple-400' : 'text-gray-500 border-transparent hover:text-gray-300'
              }`}
            >
              Copilot
            </button>
          </div>
          <div className="flex-1 overflow-hidden">
            {isCopilotOpen ? <CopilotPanel /> : <SimulatedChat />}
          </div>
        </div>
      </div>

      {/* Inspector drawer (absolute positioned, z-50) */}
      <NodeInspectorDrawer />
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ReactFlowProvider>
        <AppShell />
        <Toaster position="bottom-right" theme="dark" />
      </ReactFlowProvider>
    </QueryClientProvider>
  )
}
