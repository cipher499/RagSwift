"use client"

import { useEffect } from "react"
import { PlusIcon, MessageSquareIcon } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { api } from "@/lib/api"
import { useStore } from "@/lib/store"

export default function Sidebar() {
  const chats = useStore((s) => s.chats)
  const activeChatId = useStore((s) => s.activeChatId)
  const setChats = useStore((s) => s.setChats)
  const setDocuments = useStore((s) => s.setDocuments)
  const prependChat = useStore((s) => s.prependChat)
  const setActiveChatId = useStore((s) => s.setActiveChatId)
  const setMessages = useStore((s) => s.setMessages)

  useEffect(() => {
    api
      .listChats()
      .then((r) => setChats(r.chats))
      .catch((e) => toast.error(e.message))

    api
      .listDocuments()
      .then((r) => setDocuments(r.documents))
      .catch((e) => toast.error(e.message))
  }, [setChats, setDocuments])

  async function handleNewChat() {
    try {
      const chat = await api.createChat()
      prependChat(chat)
      setActiveChatId(chat.id)
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  async function handleSelectChat(id: string) {
    setActiveChatId(id)
    try {
      const { messages } = await api.getChat(id)
      setMessages(id, messages)
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  const sorted = [...chats].sort(
    (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
  )

  return (
    <div className="flex h-full flex-col border-r bg-muted/30">
      <div className="flex items-center justify-between p-3 border-b">
        <span className="text-sm font-semibold">Chats</span>
        <Button size="icon" variant="ghost" onClick={handleNewChat} title="New chat">
          <PlusIcon className="h-4 w-4" />
        </Button>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-2 space-y-0.5">
          {sorted.map((chat) => (
            <button
              key={chat.id}
              onClick={() => handleSelectChat(chat.id)}
              className={`w-full flex items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-accent ${
                chat.id === activeChatId ? "bg-accent text-accent-foreground font-medium" : "text-muted-foreground"
              }`}
            >
              <MessageSquareIcon className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">{chat.title}</span>
            </button>
          ))}
          {sorted.length === 0 && (
            <p className="px-2 py-3 text-xs text-muted-foreground text-center">No chats yet</p>
          )}
        </div>
      </ScrollArea>
    </div>
  )
}
