"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";

const NAV = [
  { href: "/", label: "نمای کلی" },
  { href: "/live", label: "معاملات زنده" },
  { href: "/scanner", label: "اسکنر بازار" },
  { href: "/positions", label: "پوزیشن‌ها" },
  { href: "/orders", label: "سفارش‌ها" },
  { href: "/strategies", label: "استراتژی‌ها" },
  { href: "/risk", label: "ریسک" },
  { href: "/performance", label: "عملکرد" },
  { href: "/journal", label: "ژورنال" },
  { href: "/backtest", label: "بک‌تست" },
  { href: "/health", label: "سلامت سیستم" },
  { href: "/settings", label: "تنظیمات" },
];

export function Sidebar() {
  const path = usePathname();
  return (
    <aside className="flex w-60 shrink-0 flex-col border-l border-white/10 bg-slate-950/35 backdrop-blur-xl">
      <div className="flex items-center gap-3 border-b border-white/10 p-5">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-400 to-amber-400 text-sm font-black text-slate-950 shadow-glow">
          FX
        </div>
        <div>
          <div className="aurora text-sm font-bold">Molido Trade</div>
          <div className="text-[11px] text-slate-400">LIVE deck v0.2</div>
        </div>
      </div>
      <nav className="flex-1 space-y-0.5 overflow-y-auto p-3 text-sm">
        {NAV.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={clsx(
              "flex items-center gap-3 rounded-xl px-3 py-2.5 transition",
              path === item.href
                ? "border border-cyan-400/25 bg-cyan-400/10 text-cyan-200"
                : "text-slate-300 hover:bg-white/5"
            )}
          >
            {item.label}
          </Link>
        ))}
      </nav>
      <div className="border-t border-white/10 p-4 text-xs">
        <div className="mb-1 text-slate-500">وضعیت ربات</div>
        <div className="flex items-center justify-between">
          <span className="font-medium text-emerald-300">روشن · LIVE</span>
          <div className="relative h-5 w-10 rounded-full bg-emerald-500">
            <div className="absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-white" />
          </div>
        </div>
      </div>
    </aside>
  );
}
