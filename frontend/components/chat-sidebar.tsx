"use client";

import { useEffect, useRef } from "react";
import { Plus, Trash2, MessageSquare } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/lib/store";
import { getChats, createChat, deleteChat } from "@/lib/api";
import type { Chat } from "@/types";

export function ChatSidebar() {
  const { chats, activeChatId, setChats, prependChat, removeChat, setActiveChatId, setMessages } =
    useAppStore();
  const loadedRef = useRef(false);

  useEffect(() => {
    if (loadedRef.current) return;
    loadedRef.current = true;
    getChats()
      .then(setChats)
      .catch(() => toast.error("Failed to load chats"));
  }, [setChats]);

  async function handleNewChat() {
    try {
      const chat = await createChat();
      prependChat(chat);
      setActiveChatId(chat.id);
      setMessages(chat.id, []);
    } catch {
      toast.error("Failed to create chat");
    }
  }

  async function handleDeleteChat(e: React.MouseEvent, chat: Chat) {
    e.stopPropagation();
    try {
      await deleteChat(chat.id);
      removeChat(chat.id);
    } catch {
      toast.error("Failed to delete chat");
    }
  }

  return (
    <div className="flex h-full flex-col border-r bg-muted/30">
      {/* Brand */}
      <div className="px-4 py-3 border-b">
        <span className="text-base font-bold tracking-tight">RAGSwift</span>
      </div>

      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b">
        <span className="text-sm font-semibold">Chats</span>
        <button
          onClick={handleNewChat}
          title="New chat"
          className="flex items-center justify-center size-8 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
        >
          <Plus className="size-4" />
        </button>
      </div>

      {/* Chat list */}
      <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
        {chats.length === 0 ? (
          <p className="px-2 py-3 text-xs text-muted-foreground text-center">No chats yet</p>
        ) : (
          chats.map((chat) => (
            <ChatItem
              key={chat.id}
              chat={chat}
              active={chat.id === activeChatId}
              onSelect={() => setActiveChatId(chat.id)}
              onDelete={(e) => handleDeleteChat(e, chat)}
            />
          ))
        )}
      </div>
    </div>
  );
}

function ChatItem({
  chat,
  active,
  onSelect,
  onDelete,
}: {
  chat: Chat;
  active: boolean;
  onSelect: () => void;
  onDelete: (e: React.MouseEvent) => void;
}) {
  return (
    <button
      onClick={onSelect}
      className={cn(
        "group flex w-full items-center gap-2 rounded-md px-2 py-2 text-sm transition-colors text-left",
        active
          ? "bg-accent text-accent-foreground"
          : "text-muted-foreground hover:bg-muted hover:text-foreground"
      )}
    >
      <MessageSquare className="size-3.5 shrink-0" />
      <span className="flex-1 truncate">{chat.title}</span>
      <span
        role="button"
        onClick={onDelete}
        title="Delete chat"
        className="opacity-0 group-hover:opacity-100 flex items-center justify-center size-5 rounded hover:text-destructive transition-opacity"
      >
        <Trash2 className="size-3.5" />
      </span>
    </button>
  );
}
