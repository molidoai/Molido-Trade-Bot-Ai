import { TiltCard } from "@/components/ui/TiltCard";

const STRATS = ["Trend Following", "Donchian Breakout", "RSI Mean Reversion"];

export default function Page() {
  return (
    <div className="space-y-6">
      <h2 className="aurora text-3xl font-black">استراتژی‌ها</h2>
      <div className="grid gap-4 md:grid-cols-3">
        {STRATS.map((s) => (
          <TiltCard key={s}>
            <p className="font-medium">{s}</p>
            <p className="mt-2 text-xs text-emerald-300">فعال</p>
          </TiltCard>
        ))}
      </div>
    </div>
  );
}
