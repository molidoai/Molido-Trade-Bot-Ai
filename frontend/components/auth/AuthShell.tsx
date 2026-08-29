"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Sidebar } from "@/components/layout/Sidebar";
import { TopBar } from "@/components/layout/TopBar";
import { EnvBanner } from "@/components/layout/EnvBanner";
import { API, clearSession, getMeta, getToken } from "@/lib/auth";

export function AuthShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [ok, setOk] = useState(path === "/login");
  const meta = getMeta();

  useEffect(() => {
    if (path === "/login") {
      const t = getToken();
      if (t) {
        void fetch(`${API}/auth/me`, { headers: { Authorization: `Bearer ${t}` } }).then((r) => {
          if (r.ok) router.replace("/");
        });
      }
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

  if (path === "/login") {
    return <>{children}</>;
  }

  if (!ok) {
    return (
      <div className="flex h-screen items-center justify-center text-sm text-slate-400">
        در حال بررسی نشست مالک…
      </div>
    );
  }

  return (
    <div className="relative z-10 flex h-screen flex-col">
      <EnvBanner />
      <div className="flex min-h-0 flex-1">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          <TopBar />
          <div className="flex items-center justify-between border-b border-white/5 px-6 py-1 text-[11px] text-slate-500">
            <span>
              {meta.email || "owner"} · {meta.session_ip || "session"}
              {meta.last_login_at ? ` · ورود قبلی ${meta.last_login_at}` : ""}
            </span>
            <button
              type="button"
              className="text-amber-300/80 hover:text-amber-200"
              onClick={() => {
                clearSession();
                router.replace("/login");
              }}
            >
              خروج
            </button>
          </div>
          <main className="flex-1 overflow-y-auto p-6">{children}</main>
        </div>
      </div>
    </div>
  );
}
