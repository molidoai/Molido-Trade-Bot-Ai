"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";

const NAV = [
  { href: "/", label: "نمای کلی", icon: "◉" },
  { href: "/live", label: "معاملات زنده", icon: "↗" },
  { href: "/scanner", label: "اسکنر بازار", icon: "⌕" },
  { href: "/positions", label: "پوزیشن‌ها", icon: "▤" },
  { href: "/orders", label: "سفارش‌ها", icon: "☰" },
  { href: "/strategies", label: "استراتژی‌ها", icon: "⚙" },
  { href: "/risk", label: "ریسک", icon: "⛨" },
  { href: "/performance", label: "عملکرد", icon: "▤" },
  { href: "/journal", label: "ژورنال", icon: "✎" },
  { href: "/backtest", label: "بک‌تست", icon: "◈" },
  { href: "/health", label: "سلامت سیستم", icon: "◎" },
  { href: "/settings", label: "تنظیمات", icon: "⚙" },
];

export function Sidebar() {
  const path = usePathname();
  return (
    <aside className="w-60 shrink-0 border-l border-slate-800 bg-slate-900 flex flex-col">
      <div className="p-5 border-b border-slate-800 flex items-center gap-3">
        <div className="w-9 h-9 rounded-lg bg-brand-600 flex items-center justify-center font-bold">FX</div>
        <div>
          <div className="font-semibold text-sm">Molido Trade</div>
          <div className="text-xs text-slate-400">Bot AI v0.1</div>
        </div>
      </div>
      <nav className="flex-1 overflow-y-auto p-3 space-y-0.5 text-sm">
        {NAV.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={clsx(
              "flex items-center gap-3 px-3 py-2.5 rounded-lg transition",
              path === item.href
                ? "bg-brand-600/20 text-brand-400 border border-brand-500/20"
                : "text-slate-300 hover:bg-slate-800"
            )}
          >
            <span className="w-5 text-center opacity-70">{item.icon}</span>
            {item.label}
          </Link>
        ))}
      </nav>
      <div className="p-4 border-t border-slate-800 text-xs">
        <div className="text-slate-500 mb-1">وضعیت ربات</div>
        <div className="flex items-center justify-between">
          <span className="text-emerald-400 font-medium">روشن (ON)</span>
          <div className="w-10 h-5 bg-emerald-500 rounded-full relative">
            <div className="absolute left-0.5 top-0.5 w-4 h-4 bg-white rounded-full" />
          </div>
        </div>
      </div>
    </aside>
  );
}
