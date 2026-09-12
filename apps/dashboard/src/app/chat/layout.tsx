import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "智能问答 | STRA",
  description: "Ask questions about game reviews using AI-powered natural language analysis.",
};

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  return children;
}
