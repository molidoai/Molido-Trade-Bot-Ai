import type { Metadata, Viewport } from "next";
import "./globals.css";
import { Scene3D } from "@/components/scene/Scene3D";
import { AuthShell } from "@/components/auth/AuthShell";
import { AppProviders } from "@/components/app/Providers";

export const metadata: Metadata = {
  title: "Molido Trade",
  description: "Molido Trade Bot AI",
  applicationName: "Molido Trade",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    title: "Molido Trade",
    statusBarStyle: "black-translucent",
  },
  icons: { icon: "/logo.svg", apple: "/logo.svg" },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#040612" },
    { media: "(prefers-color-scheme: light)", color: "#eef3f9" },
  ],
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fa" dir="rtl" className="dark" suppressHydrationWarning>
      <body className="min-h-dvh">
        <AppProviders>
          <Scene3D />
          <AuthShell>{children}</AuthShell>
        </AppProviders>
      </body>
    </html>
  );
}
