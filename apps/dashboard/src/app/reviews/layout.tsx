import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "玩家评论 | STRA",
  description: "Explore classified Steam reviews by category, recommendation, and taxonomy.",
};

export default function ReviewsLayout({ children }: { children: React.ReactNode }) {
  return children;
}
