"use client";

export function TopBar() {
  return (
    <header className="sticky top-0 z-10 border-b border-slate-800 bg-slate-950/80 backdrop-blur px-6 py-3 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-semibold">نمای کلی</h1>
        <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
          DEMO
        </span>
        <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-500/20 text-emerald-400">
          ربات: روشن
        </span>
      </div>
      <div className="flex items-center gap-4 text-sm">
        <div className="text-left">
          <div className="text-xs text-slate-400">Account Health</div>
          <div className="font-semibold text-emerald-400">۸۷ / ۱۰۰</div>
        </div>
        <div className="h-8 w-px bg-slate-700" />
        <button className="px-3 py-1.5 rounded-lg bg-rose-600/20 text-rose-400 border border-rose-500/30 text-sm hover:bg-rose-600/30">
          Kill Switch
        </button>
      </div>
    </header>
  );
}
