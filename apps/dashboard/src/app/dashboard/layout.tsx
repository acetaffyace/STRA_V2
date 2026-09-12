import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "数据总览 | STRA",
  description: "Analyze Steam game reviews with AI-powered classification and actionable insights.",
};

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return children;
}
