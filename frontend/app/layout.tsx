import type { Metadata } from "next"
import { Geist, Geist_Mono } from "next/font/google"
import "./globals.css"
import { Toaster } from "sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import Sidebar from "@/components/sidebar"
import TracePanel from "@/components/trace-panel"
import AppShell from "./app-shell"

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
})

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
})

export const metadata: Metadata = {
  title: "RAGSwift",
  description: "Retrieval-Augmented Generation MVP",
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="h-full overflow-hidden">
        <TooltipProvider>
          <div className="flex h-full">
            {/* Sidebar — fixed 240px */}
            <div className="w-60 shrink-0 hidden lg:flex flex-col h-full">
              <Sidebar />
            </div>

            {/* Main column — flex-1 */}
            <main className="flex-1 min-w-0 overflow-auto">
              {children}
            </main>

            {/* Trace panel — 320px, collapsible, hidden until first assistant message */}
            <AppShell>
              <TracePanel />
            </AppShell>
          </div>
          <Toaster richColors position="top-right" />
        </TooltipProvider>
      </body>
    </html>
  )
}
