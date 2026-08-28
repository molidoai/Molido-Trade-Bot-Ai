import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "@/components/layout/Sidebar";
import { TopBar } from "@/components/layout/TopBar";
import { EnvBanner } from "@/components/layout/EnvBanner";

export const metadata: Metadata = {
  title: "Molido Trade Bot AI",
  description: "Professional Automated Forex Trading Platform – no profit guarantee",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fa" dir="rtl" className="dark">
      <body className="min-h-screen">
        <EnvBanner />
        <div className="flex h-[calc(100vh-36px)]">
          <Sidebar />
          <div className="flex flex-1 flex-col overflow-hidden">
            <TopBar />
            <main className="flex-1 overflow-y-auto p-6">{children}</main>
          </div>
        </div>
      </body>
    </html>
  );
}
