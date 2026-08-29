"use client";

export function TopBar() {
  return (
    <header className="sticky top-0 z-10 flex items-center justify-between border-b border-white/10 bg-slate-950/40 px-6 py-3 backdrop-blur-xl">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-semibold">نمای کلی</h1>
        <span className="rounded-full border border-rose-400/40 bg-rose-500/15 px-2.5 py-0.5 text-xs font-bold text-rose-300">
          REAL
        </span>
        <span className="rounded-full border border-emerald-400/30 bg-emerald-500/15 px-2.5 py-0.5 text-xs font-medium text-emerald-300">
          ربات: روشن
        </span>
      </div>
      <div className="flex items-center gap-4 text-sm">
        <div className="text-left">
          <div className="text-xs text-slate-400">Live pulse</div>
          <div className="font-semibold text-cyan-300">فعال</div>
        </div>
        <div className="h-8 w-px bg-white/10" />
        <button className="rounded-lg border border-rose-500/40 bg-rose-600/20 px-3 py-1.5 text-sm text-rose-300 hover:bg-rose-600/35">
          Kill Switch
        </button>
      </div>
    </header>
  );
}
