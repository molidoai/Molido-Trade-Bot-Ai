"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import clsx from "clsx";
import { useApp } from "@/components/app/Providers";
import { API } from "@/lib/auth";

/**
 * Thirteen links in one flat list gave no sense of which pages matter daily and
 * which are occasional, so they are grouped by what you are trying to do:
 * watch it trade, understand what it did, or change how it behaves.
 */
const GROUPS: { title: string; items: { href: string; label: string }[] }[] = [
  {
    title: "معاملات",
    items: [
      { href: "/home", label: "نمای کلی" },
      { href: "/live", label: "معاملات زنده" },
      { href: "/positions", label: "پوزیشن‌ها" },
      { href: "/orders", label: "سفارش‌ها" },
      { href: "/scanner", label: "اسکنر بازار" },
    ],
  },
  {
    title: "تحلیل",
    items: [
      { href: "/performance", label: "عملکرد" },
      { href: "/journal", label: "ژورنال" },
      { href: "/backtest", label: "بک‌تست" },
    ],
  },
  {
    title: "پیکربندی",
    items: [
      { href: "/accounts", label: "حساب‌ها" },
      { href: "/strategies", label: "استراتژی‌ها" },
      { href: "/risk", label: "ریسک" },
      { href: "/settings", label: "تنظیمات" },
    ],
  },
  {
    title: "سیستم",
    items: [{ href: "/health", label: "سلامت سیستم" }],
  },
];

type Status = { master_bot_enabled?: boolean; account_mode?: string; trading_hours_ok?: boolean };

/**
 * The bot status used to be hardcoded to "روشن" with a green toggle painted
 * on. It said the bot was running while it was stopped, which is worse than
 * showing nothing: a dashboard that cannot be wrong about this is the whole
 * reason to open it. It now reads the real value, and says plainly when it
 * could not.
 */
function BotStatus() {
  const [s, setS] = useState<Status | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    const read = async () => {
      try {
        const r = await fetch(`${API}/system/status`, { cache: "no-store" });
        if (!r.ok) throw new Error(String(r.status));
        const d = await r.json();
        if (alive) { setS(d); setFailed(false); }
      } catch {
        if (alive) setFailed(true);
      }
    };
    void read();
    const t = setInterval(read, 20000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  if (failed || !s) {
    return (
      <div className="flex items-center justify-between">
        <span className="text-[var(--muted)]">{failed ? "بی‌پاسخ" : "..."}</span>
        <div className="h-5 w-10 rounded-full bg-white/10" />
      </div>
    );
  }

  const on = !!s.master_bot_enabled;
  return (
    <>
      <div className="flex items-center justify-between">
        <span className={clsx("font-medium",
          on ? "text-emerald-600 dark:text-emerald-300" : "text-[var(--muted)]")}>
          {on ? "روشن" : "خاموش"}
        </span>
        <div className={clsx("relative h-5 w-10 rounded-full transition",
          on ? "bg-emerald-500" : "bg-white/15")}>
          <div className={clsx("absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all",
            on ? "left-5" : "left-0.5")} />
        </div>
      </div>
      <div className="mt-2 flex items-center gap-2 text-[11px] text-[var(--muted)]">
        <span className={clsx("rounded px-1.5 py-0.5",
          s.account_mode === "REAL"
            ? "bg-amber-400/15 text-amber-300"
            : "bg-white/5")}>
          {s.account_mode || "—"}
        </span>
        {/* Being switched on is not the same as being able to trade. */}
        <span>{s.trading_hours_ok ? "در ساعت معاملاتی" : "خارج از ساعت"}</span>
      </div>
    </>
  );
}

export function Sidebar() {
  const path = usePathname();
  const { navOpen, setNavOpen, theme, toggle } = useApp();

  return (
    <>
      {navOpen ? (
        <button
          type="button"
          aria-label="بستن منو"
          className="fixed inset-0 z-30 bg-black/50 md:hidden"
          onClick={() => setNavOpen(false)}
        />
      ) : null}
      <aside
        className={clsx(
          "fixed inset-y-0 right-0 z-40 flex w-64 shrink-0 flex-col border-white/10 bg-[var(--panel)] backdrop-blur-xl transition-transform md:static md:z-0 md:w-60 md:translate-x-0 md:border-l",
          navOpen ? "translate-x-0" : "translate-x-full md:translate-x-0"
        )}
      >
        <div className="flex items-center gap-3 border-b border-[var(--line)] p-5">
          <img src="/logo.svg" alt="Molido Trade" width={40} height={40} className="h-10 w-10 rounded-xl" />
          <div>
            <div className="aurora text-sm font-bold">Molido Trade</div>
            <div className="text-[11px] text-[var(--muted)]">وب‌اپ دسکتاپ و موبایل</div>
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto p-3 text-sm">
          {GROUPS.map((g) => (
            <div key={g.title} className="mb-4 last:mb-0">
              <div className="px-3 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--muted)]">
                {g.title}
              </div>
              <div className="space-y-0.5">
                {g.items.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setNavOpen(false)}
                    aria-current={path === item.href ? "page" : undefined}
                    className={clsx(
                      "flex items-center gap-3 rounded-xl px-3 py-2.5 transition",
                      path === item.href
                        ? "border border-cyan-400/25 bg-cyan-400/10 text-cyan-700 dark:text-cyan-200"
                        : "text-[var(--ink)] hover:bg-black/5 dark:hover:bg-white/5"
                    )}
                  >
                    {item.label}
                  </Link>
                ))}
              </div>
            </div>
          ))}
        </nav>

        <div className="border-t border-[var(--line)] p-4 text-xs">
          <button
            type="button"
            onClick={toggle}
            className="mb-3 w-full rounded-xl border border-[var(--line)] px-3 py-2 text-sm"
          >
            {theme === "dark" ? "حالت روشن" : "حالت تاریک"}
          </button>
          <div className="mb-1 text-[var(--muted)]">وضعیت ربات</div>
          <BotStatus />
        </div>
      </aside>
    </>
  );
}
