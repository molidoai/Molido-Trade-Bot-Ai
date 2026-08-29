"use client";

export function EnvBanner() {
  return (
    <div className="relative overflow-hidden border-b border-amber-400/20 bg-gradient-to-l from-rose-600/90 via-amber-500/80 to-cyan-500/70 py-1.5 text-center text-sm font-medium tracking-wide text-white">
      <span className="gold-live ml-2 inline-block h-2 w-2 rounded-full bg-white" />
      محیط فعلی: <span className="font-black">LIVE / REAL</span>
      {" · "}
      سرمایه واقعی درگیر است · هیچ تضمین سودی وجود ندارد
    </div>
  );
}
