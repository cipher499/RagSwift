import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Toaster } from "sonner";
import { ChatSidebar } from "@/components/chat-sidebar";
import "./globals.css";

const geist = Geist({ subsets: ["latin"], variable: "--font-geist" });
const geistMono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono" });

export const metadata: Metadata = {
  title: "RAGSwift",
  description: "Retrieval-Augmented Generation MVP",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${geist.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="h-full overflow-hidden">
        <div className="flex h-full">
          <div className="w-60 shrink-0 hidden lg:flex flex-col h-full">
            <ChatSidebar />
          </div>
          <main className="flex-1 min-w-0 flex overflow-hidden">{children}</main>
        </div>
        <Toaster richColors position="top-right" />
      </body>
    </html>
  );
}
