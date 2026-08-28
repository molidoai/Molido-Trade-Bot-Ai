"use client";

export function EnvBanner() {
  // In production this comes from API /system/status
  const mode = "DEMO";
  return (
    <div className="bg-emerald-600/90 text-center py-1.5 text-sm font-medium tracking-wide text-white">
      محیط فعلی: <span className="font-bold">{mode}</span> — هیچ سرمایه واقعی درگیر نیست · بدون تضمین سود
    </div>
  );
}
