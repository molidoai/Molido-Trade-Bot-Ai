import { TiltCard } from "@/components/ui/TiltCard";

export default function Page() {
  return (
    <div className="space-y-6">
      <h2 className="aurora text-3xl font-black">اسکنر بازار</h2>
      <TiltCard>
        <p className="text-slate-300">اسکنر روی EURUSD، GBPUSD و XAUUSD گوش می‌دهد.</p>
      </TiltCard>
    </div>
  );
}
