import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "游戏对比 | STRA",
  description: "Compare Steam games side-by-side with category breakdowns and trend analysis.",
};

export default function CompareLayout({ children }: { children: React.ReactNode }) {
  return children;
}
