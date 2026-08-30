import { TiltCard } from "@/components/ui/TiltCard";
import { FlattenButton } from "./FlattenButton";
import { BrainPanel } from "./BrainPanel";
import { AccountControl } from "./AccountControl";

export default function Page() {
  return (
    <div className="space-y-6">
      <h2 className="aurora text-3xl font-black">معاملات زنده</h2>
      <div className="grid gap-4 md:grid-cols-3">
        <TiltCard>
          <p className="text-xs text-slate-400">نمادها</p>
          <p className="mt-2 text-lg font-semibold">auto · brain universe</p>
        </TiltCard>
        <TiltCard>
          <p className="text-xs text-slate-400">تایم‌فریم</p>
          <p className="mt-2 text-lg font-semibold">AUTO / M15</p>
        </TiltCard>
        <TiltCard>
          <p className="text-xs text-slate-400">اجرا</p>
          <p className="mt-2 text-lg font-semibold text-rose-300">DEMO default / MT5</p>
        </TiltCard>
      </div>
      <div className="glass rounded-2xl p-8 text-sm text-slate-300 space-y-4">
        <p>
          موتور زنده بعد از اتصال MT5 سفارش می‌فرستد. تا وقتی لاگین REAL خالی باشد، رانر بالا نمی‌آید.
        </p>
        <FlattenButton />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <AccountControl />
        <BrainPanel />
      </div>
    </div>
  );
}
