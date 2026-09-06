"use client";

/**
 * The application shell.
 *
 * Replaces a 240px right sidebar plus a top bar. Two reasons, both structural
 * rather than cosmetic.
 *
 * This app is mostly wide tables -- positions, orders, journal, backtest
 * folds. A fixed rail spent a quarter of a laptop's width on thirteen links
 * that are read once per visit, and pushed the tables into horizontal scroll.
 * Navigation moves to a single horizontal row and the content gets the screen.
 *
 * And the state you actually need continuously -- is the bot on, which
 * account, is the market open, is the breaker tripped -- was scattered between
 * a sidebar footer and a top bar, both of which had it hardcoded. It is now
 * one strip, always visible, always read from the API, and it says so when it
 * cannot read it.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import clsx from "clsx";
import { API, getToken } from "@/lib/auth";
import { useApp } from "@/components/app/Providers";

const NAV: { href: string; label: string }[] = [
  { href: "/home", label: "نمای کلی" },
  { href: "/live", label: "زنده" },
  { href: "/positions", label: "پوزیشن‌ها" },
  { href: "/orders", label: "سفارش‌ها" },
  { href: "/scanner", label: "اسکنر" },
  { href: "/performance", label: "عملکرد" },
  { href: "/journal", label: "ژورنال" },
  { href: "/backtest", label: "بک‌تست" },
  { href: "/strategies", label: "استراتژی‌ها" },
  { href: "/accounts", label: "حساب‌ها" },
  { href: "/risk", label: "ریسک" },
  { href: "/settings", label: "تنظیمات" },
  { href: "/health", label: "سلامت" },
];

type Status = {
  master_bot_enabled?: boolean;
  account_mode?: string;
  trading_hours_ok?: boolean;
  circuit_breaker?: string;
  database?: string;
  redis?: string;
  news_blackout?: boolean;
};

/** One reading of live state. `null` means "not known", which is rendered as
 *  not known rather than as a healthy default -- the previous shell defaulted
 *  master to `true` and the mode to "DEMO" in component state, so it claimed
 *  the bot was running before it had asked anything. */
function useStatus() {
  const [s, setS] = useState<Status | null>(null);
  const [stale, setStale] = useState(false);
  useEffect(() => {
    let alive = true;
    const read = async () => {
      try {
        const r = await fetch(`${API}/system/status`, { cache: "no-store" });
        if (!r.ok) throw new Error(String(r.status));
        const d = await r.json();
        if (alive) { setS(d); setStale(false); }
      } catch {
        if (alive) setStale(true);
      }
    };
    void read();
    const t = setInterval(read, 15000);
    return () => { alive = false; clearInterval(t); };
  }, []);
  return { s, stale };
}

function Dot({ tone }: { tone: "up" | "down" | "warn" | "mute" }) {
  const c = { up: "var(--up)", down: "var(--down)", warn: "var(--warn)", mute: "var(--muted)" }[tone];
  return <span className="inline-block h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: c }} />;
}

/** A labelled reading. The label is always present: an unlabelled coloured dot
 *  is unreadable to anyone who cannot separate the hues, and unmemorable to
 *  everyone else. */
function Stat({ label, value, tone = "mute" }: {
  label: string; value: string; tone?: "up" | "down" | "warn" | "mute";
}) {
  return (
    <div className="flex items-baseline gap-1.5 whitespace-nowrap">
      <span className="text-[10px] text-[var(--muted)]">{label}</span>
      <span className="flex items-center gap-1 text-[11px] font-medium">
        <Dot tone={tone} />
        {value}
      </span>
    </div>
  );
}

function StatusStrip() {
  const { s, stale } = useStatus();

  if (!s) {
    return (
      <div className="flex items-center gap-2 text-[11px] text-[var(--muted)]">
        <Dot tone="mute" />
        {stale ? "وضعیت در دسترس نیست" : "در حال خواندن وضعیت…"}
      </div>
    );
  }

  const real = s.account_mode === "REAL";
  const breakerOpen = (s.circuit_breaker || "").toLowerCase() === "active";

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
      <Stat label="ربات" value={s.master_bot_enabled ? "روشن" : "خاموش"}
        tone={s.master_bot_enabled ? "up" : "mute"} />
      <Stat label="حساب" value={s.account_mode || "—"} tone={real ? "warn" : "mute"} />
      <Stat label="بازار" value={s.trading_hours_ok ? "باز" : "بسته"}
        tone={s.trading_hours_ok ? "up" : "mute"} />
      {breakerOpen ? <Stat label="مدار" value="قطع" tone="down" /> : null}
      {s.news_blackout ? <Stat label="اخبار" value="توقف" tone="warn" /> : null}
      {s.database !== "connected" || s.redis !== "connected"
        ? <Stat label="سرویس" value="اختلال" tone="down" /> : null}
      {stale ? <Stat label="داده" value="کهنه" tone="warn" /> : null}
    </div>
  );
}

function KillSwitch() {
  const [busy, setBusy] = useState(false);
  const [armed, setArmed] = useState(false);
  const [msg, setMsg] = useState("");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);

  async function fire() {
    setBusy(true); setMsg("");
    try {
      const token = getToken();
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers.Authorization = `Bearer ${token}`;
      const r = await fetch(`${API}/ops/master`, {
        method: "POST", headers,
        body: JSON.stringify({ enabled: false, actor: "dashboard-kill-switch" }),
      });
      if (r.status === 401 || r.status === 403) setMsg("فقط با ورود مالک");
      else if (!r.ok) setMsg("خطا");
      else setMsg("ورود جدید قطع شد");
    } catch { setMsg("API در دسترس نیست"); }
    finally { setBusy(false); setArmed(false); }
  }

  // Two steps. This stops the bot opening anything new, and it sat one stray
  // click away from a mobile thumb.
  if (!armed) {
    return (
      <div className="flex items-center gap-2">
        {msg ? <span className="text-[11px] text-[var(--muted)]">{msg}</span> : null}
        <button type="button" className="btn btn-danger h-8 min-h-0 px-3 text-xs"
          onClick={() => {
            setArmed(true);
            timer.current = setTimeout(() => setArmed(false), 5000);
          }}>
          توقف اضطراری
        </button>
      </div>
    );
  }
  return (
    <div className="flex items-center gap-1.5">
      <button type="button" disabled={busy} onClick={fire}
        className="btn h-8 min-h-0 border-transparent px-3 text-xs"
        style={{ background: "var(--down)", color: "#fff" }}>
        {busy ? "…" : "مطمئنم، متوقف کن"}
      </button>
      <button type="button" className="btn h-8 min-h-0 px-2 text-xs" onClick={() => setArmed(false)}>
        انصراف
      </button>
    </div>
  );
}

export function AppShell({
  children, email, onLogout,
}: {
  children: React.ReactNode;
  email?: string;
  onLogout: () => void;
}) {
  const path = usePathname();
  const { theme, toggle } = useApp();

  return (
    <div className="flex min-h-dvh flex-col" style={{ background: "var(--bg)" }}>
      <header className="sticky top-0 z-20 border-b"
        style={{ background: "var(--surface)", borderColor: "var(--line)" }}>
        {/* identity + live state + controls */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2.5 md:px-6">
          <Link href="/home" className="flex shrink-0 items-center gap-2">
            <img src="/logo.svg" alt="" width={26} height={26} className="h-6.5 w-6.5 rounded-md" />
            <span className="text-[13px] font-bold tracking-tight">Molido</span>
          </Link>

          <div className="mx-1 hidden h-5 w-px shrink-0 sm:block" style={{ background: "var(--line)" }} />

          <StatusStrip />

          <div className="ms-auto flex shrink-0 items-center gap-2">
            <button type="button" onClick={toggle} aria-label="تغییر تم"
              className="btn h-8 min-h-0 px-2.5 text-xs">
              {theme === "dark" ? "روشن" : "تاریک"}
            </button>
            <KillSwitch />
          </div>
        </div>

        {/* navigation: one row, scrollable rather than wrapped, so its height
            never changes and the content below does not jump */}
        <nav className="flex gap-1 overflow-x-auto px-3 pb-1.5 md:px-5"
          style={{ scrollbarWidth: "thin" }}>
          {NAV.map((n) => {
            const active = path === n.href;
            return (
              <Link key={n.href} href={n.href}
                aria-current={active ? "page" : undefined}
                className={clsx(
                  "shrink-0 rounded-lg px-3 py-1.5 text-[12.5px] transition-colors",
                  active ? "font-medium" : "text-[var(--ink-2)] hover:text-[var(--ink)]"
                )}
                style={active
                  ? { background: "var(--brand-soft)", color: "var(--brand)" }
                  : undefined}>
                {n.label}
              </Link>
            );
          })}
        </nav>
      </header>

      <main className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-5 md:px-6">
        {children}
      </main>

      <footer className="mt-auto border-t px-4 py-2.5 text-[11px] md:px-6"
        style={{ borderColor: "var(--line)", color: "var(--muted)" }}>
        <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-3">
          <span className="truncate">{email || "owner"}</span>
          <button type="button" onClick={onLogout} className="shrink-0 hover:text-[var(--ink)]">
            خروج
          </button>
        </div>
      </footer>
    </div>
  );
}
