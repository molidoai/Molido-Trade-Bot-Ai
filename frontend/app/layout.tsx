import type { Metadata } from "next";
import "./globals.css";
import { Scene3D } from "@/components/scene/Scene3D";
import { AuthShell } from "@/components/auth/AuthShell";

export const metadata: Metadata = {
  title: "Molido Trade · LIVE",
  description: "Molido Trade Bot AI — live forex command deck",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fa" dir="rtl" className="dark">
      <body className="min-h-screen">
        <Scene3D />
        <AuthShell>{children}</AuthShell>
      </body>
    </html>
  );
}
