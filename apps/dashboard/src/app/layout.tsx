import clsx from "clsx";
import type { Metadata } from "next";
import "./globals.css";
import { RootProviders } from "@/components/RootProviders";

export const metadata: Metadata = {
  title: "STRA - Steam Reviews Analysis",
  description: "Steam player voice and review analysis platform",
  icons: {
    icon: "/icon.svg",
    apple: "/apple-icon.svg",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN" className="dark">
      <body
        className={clsx(
          "min-h-screen bg-slate-950 text-slate-100 antialiased"
        )}
      >
        <RootProviders>{children}</RootProviders>
      </body>
    </html>
  );
}
