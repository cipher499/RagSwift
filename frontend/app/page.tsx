"use client"

import { useStore } from "@/lib/store"
import UploadPanel from "@/components/upload-panel"
import ChatArea from "@/components/chat-area"

export default function Home() {
  const activeChatId = useStore((s) => s.activeChatId)

  if (activeChatId === null) {
    return <UploadPanel />
  }

  return <ChatArea />
}
