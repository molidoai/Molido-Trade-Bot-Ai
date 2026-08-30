"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";
import { useApp } from "@/components/app/Providers";

const NAV = [
  { href: "/home", label: "نمای کلی" },
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
        <nav className="flex-1 space-y-0.5 overflow-y-auto p-3 text-sm">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              onClick={() => setNavOpen(false)}
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
          <div className="flex items-center justify-between">
            <span className="font-medium text-emerald-600 dark:text-emerald-300">روشن</span>
            <div className="relative h-5 w-10 rounded-full bg-emerald-500">
              <div className="absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-white" />
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
