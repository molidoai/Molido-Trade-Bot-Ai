import { TiltCard } from "@/components/ui/TiltCard";
import { fetchHealth } from "@/lib/api";

export default async function Page() {
  const health = await fetchHealth();
  return (
    <div className="space-y-6">
      <h2 className="aurora text-3xl font-black">سلامت سیستم</h2>
      <TiltCard>
        <p className="text-sm text-slate-300">API: {health ? "ok" : "offline"}</p>
        <p className="mt-2 text-sm text-slate-400">حالت: {health?.account_mode || "REAL"}</p>
      </TiltCard>
    </div>
  );
}
