"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Sidebar } from "@/components/layout/Sidebar";
import { TopBar } from "@/components/layout/TopBar";
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
    <div className="relative z-10 flex h-dvh flex-col">
      <EnvBanner />
      <div className="flex min-h-0 flex-1">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          <TopBar />
          <div className="flex items-center justify-between gap-2 border-b border-[var(--line)] px-3 py-1 text-[11px] text-[var(--muted)] md:px-6">
            <span className="truncate">
              {meta.email || "owner"}
              {meta.session_ip ? ` · ${meta.session_ip}` : ""}
            </span>
            <button
              type="button"
              className="shrink-0 text-amber-700 dark:text-amber-300"
              onClick={() => {
                clearSession();
                router.replace("/login");
              }}
            >
              خروج
            </button>
          </div>
          <main className="flex-1 overflow-y-auto p-4 md:p-6">{children}</main>
        </div>
      </div>
    </div>
  );
}
