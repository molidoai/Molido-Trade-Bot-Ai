import { fetchHealth, fetchSystemStatus } from "@/lib/api";

function Kpi({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: string }) {
  return (
    <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-4">
      <div className="text-xs text-slate-400 mb-1">{label}</div>
      <div className={`text-xl font-semibold ${accent || ""}`}>{value}</div>
      {sub && <div className="text-xs text-slate-400 mt-1">{sub}</div>}
    </div>
  );
}

export default async function OverviewPage() {
  const health = await fetchHealth();
  const status = await fetchSystemStatus();

  const mode = health?.account_mode || status?.account_mode || "DEMO";
  const master = health?.master_bot ?? status?.master_bot_enabled ?? false;
  const apiOk = !!health;

  return (
    <div className="space-y-6">
      {/* KPI row – mock numbers until live portfolio API is wired */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <Kpi label="موجودی" value="$۱۰,۰۰۰" sub="حساب DEMO" />
        <Kpi label="اکوئیتی" value="$۱۰,۰۰۰" accent="text-emerald-400" />
        <Kpi label="سود/زیان روزانه" value="$۰.۰۰" />
        <Kpi label="دراودان" value="۰٪" sub="سقف وابسته به حالت حساب" />
        <Kpi label="پوزیشن باز" value="۰" />
        <Kpi label="حالت حساب" value={mode} accent={mode === "REAL" ? "text-rose-400" : "text-emerald-400"} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 rounded-xl border border-slate-700/50 bg-slate-800/60 p-5">
          <h2 className="font-medium mb-4">وضعیت سیستم</h2>
          <div className="space-y-3 text-sm">
            <Row label="API Backend" ok={apiOk} text={apiOk ? "متصل" : "قطع – سرور را روشن کنید"} />
            <Row label="حالت حساب" ok={mode !== "REAL"} text={mode} />
            <Row label="Master Bot" ok={master} text={master ? "روشن" : "خاموش (پیش‌فرض ایمن)"} />
            <Row label="Risk Engine" ok text="آماده" />
            <Row label="Circuit Breaker" ok text="غیرفعال" />
            <Row label="Database" ok={false} text={status?.database || "unknown"} />
          </div>
          <p className="mt-4 text-xs text-slate-500">
            این داشبورد به API روی <code className="text-slate-400">localhost:8000</code> متصل می‌شود.
            تا وقتی Backend بالا نیاید، داده‌های زنده نمایش داده نمی‌شوند.
          </p>
        </div>

        <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-5">
          <h2 className="font-medium mb-4">هشدار ایمنی</h2>
          <ul className="text-sm text-slate-300 space-y-2 list-disc list-inside">
            <li>هیچ تضمین سودی وجود ندارد</li>
            <li>پیش‌فرض همیشه DEMO است</li>
            <li>REAL فقط با تأیید دومرحله‌ای</li>
            <li>Risk Engine قابل دور زدن نیست</li>
            <li>Prop: سقف ضرر شرکت اعمال می‌شود</li>
          </ul>
        </div>
      </div>

      <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-5">
        <h2 className="font-medium mb-3">مسیر داده</h2>
        <p className="text-sm text-slate-400 font-mono dir-ltr text-left">
          Market Data → Indicators → Strategy → Signal → Risk → Execution → Broker
        </p>
      </div>
    </div>
  );
}

function Row({ label, ok, text }: { label: string; ok: boolean; text: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-slate-400">{label}</span>
      <span className="flex items-center gap-1.5">
        <span className={`w-2 h-2 rounded-full ${ok ? "bg-emerald-400" : "bg-slate-500"}`} />
        <span className={ok ? "text-emerald-400" : "text-slate-400"}>{text}</span>
      </span>
    </div>
  );
}
