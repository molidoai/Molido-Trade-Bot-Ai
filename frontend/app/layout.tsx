import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "@/components/layout/Sidebar";
import { TopBar } from "@/components/layout/TopBar";
import { EnvBanner } from "@/components/layout/EnvBanner";
import { Scene3D } from "@/components/scene/Scene3D";

export const metadata: Metadata = {
  title: "Molido Trade · LIVE",
  description: "Molido Trade Bot AI — live forex command deck",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fa" dir="rtl" className="dark">
      <body className="min-h-screen">
        <Scene3D />
        <div className="relative z-10 flex h-screen flex-col">
          <EnvBanner />
          <div className="flex min-h-0 flex-1">
            <Sidebar />
            <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
              <TopBar />
              <main className="flex-1 overflow-y-auto p-6">{children}</main>
            </div>
          </div>
        </div>
      </body>
    </html>
  );
}
