import { fetchHealth, fetchSystemStatus } from "@/lib/api";
import { TiltCard } from "@/components/ui/TiltCard";

export default async function OverviewPage() {
  const health = await fetchHealth();
  const status = await fetchSystemStatus();

  const mode = health?.account_mode || status?.account_mode || "DEMO";
  const master = health?.master_bot ?? status?.master_bot_enabled ?? true;
  const apiOk = !!health;

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.25em] text-cyan-300/80">command deck</p>
          <h2 className="aurora mt-1 text-3xl font-black">اتاق فرمان زنده</h2>
        </div>
        <div className="text-left text-xs text-slate-400">
          Market → Signal → Risk → Execution
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6">
        <Kpi label="موجودی" value="—" sub="منتظر MT5" />
        <Kpi label="اکوئیتی" value="—" accent="text-cyan-300" />
        <Kpi label="PnL روزانه" value="$۰.۰۰" />
        <Kpi label="دراودان" value="۰٪" />
        <Kpi label="پوزیشن باز" value="۰" />
        <Kpi label="حالت حساب" value={mode} accent={mode === "REAL" ? "text-rose-300" : "text-emerald-300"} />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <TiltCard className="lg:col-span-2">
          <h2 className="mb-4 font-medium">وضعیت سیستم</h2>
          <div className="space-y-3 text-sm">
            <Row label="API Backend" ok={apiOk} text={apiOk ? "متصل" : "قطع – سرور را روشن کنید"} />
            <Row label="حالت حساب" ok text={mode} />
            <Row label="Master Bot" ok={master} text={master ? "روشن · LIVE" : "خاموش"} />
            <Row label="Risk Engine" ok text="اجباری · بدون دور زدن" />
            <Row label="Circuit Breaker" ok text="آماده" />
            {/* The API reports "connected"; comparing against "ok" alone left
                this lamp red even on a healthy database. */}
            <Row
              label="Database"
              ok={status?.database === "connected" || status?.database === "ok"}
              text={status?.database || "unknown"}
            />
          </div>
        </TiltCard>

        <TiltCard>
          <h2 className="mb-4 font-medium">هشدار LIVE</h2>
          <ul className="space-y-2 text-sm text-slate-300">
            <li>سرمایه واقعی درگیر است</li>
            <li>هیچ تضمین سودی وجود ندارد</li>
            <li>Risk Engine قابل دور زدن نیست</li>
            <li>بدون Stop-Loss سفارشی ارسال نمی‌شود</li>
            <li>Kill Switch برای توقف اضطراری اینجاست</li>
          </ul>
        </TiltCard>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-7">
        {["Market", "Indicators", "Strategy", "Signal", "Risk", "Execution", "Broker"].map((step, i) => (
          <div
            key={step}
            className="glass rounded-2xl px-3 py-4 text-center text-xs font-medium text-cyan-100"
            style={{ animation: `floaty ${3 + i * 0.2}s ease-in-out infinite`, animationDelay: `${i * 0.12}s` }}
          >
            {step}
          </div>
        ))}
      </div>
    </div>
  );
}

function Kpi({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: string }) {
  return (
    <div className="glass rounded-2xl p-4">
      <div className="mb-1 text-xs text-slate-400">{label}</div>
      <div className={`text-xl font-semibold ${accent || ""}`}>{value}</div>
      {sub && <div className="mt-1 text-xs text-slate-500">{sub}</div>}
    </div>
  );
}

function Row({ label, ok, text }: { label: string; ok: boolean; text: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-slate-400">{label}</span>
      <span className="flex items-center gap-1.5">
        <span className={`h-2 w-2 rounded-full ${ok ? "bg-emerald-400" : "bg-slate-500"}`} />
        <span className={ok ? "text-emerald-300" : "text-slate-400"}>{text}</span>
      </span>
    </div>
  );
}
