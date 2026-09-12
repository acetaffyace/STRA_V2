import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "系统设置 | STRA",
  description: "Manage your account and application preferences.",
};

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  return children;
}
