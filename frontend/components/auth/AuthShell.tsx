"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { AppShell } from "@/components/layout/AppShell";
import { EnvBanner } from "@/components/layout/EnvBanner";
import { API, clearSession, getMeta, getToken } from "@/lib/auth";

const PUBLIC = new Set(["/", "/login"]);

export function AuthShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [ok, setOk] = useState(PUBLIC.has(path));
  const meta = getMeta();

  useEffect(() => {
    if (path === "/") {
      router.replace("/login");
      return;
    }
    if (path === "/login") {
      clearSession();
      setOk(true);
      return;
    }
    const t = getToken();
    if (!t) {
      router.replace("/login");
      return;
    }
    void (async () => {
      const r = await fetch(`${API}/auth/me`, {
        headers: { Authorization: `Bearer ${t}` },
        cache: "no-store",
      });
      if (!r.ok) {
        clearSession();
        router.replace("/login");
        return;
      }
      setOk(true);
    })();
  }, [path, router]);

  if (PUBLIC.has(path)) {
    return <>{children}</>;
  }

  if (!ok) {
    return (
      <div className="flex h-dvh items-center justify-center text-sm text-[var(--muted)]">
        در حال بررسی نشست مالک…
      </div>
    );
  }

  return (
    <>
      <EnvBanner />
      <AppShell
        email={meta.email}
        onLogout={() => {
          clearSession();
          router.replace("/login");
        }}
      >
        {children}
      </AppShell>
    </>
  );
}
