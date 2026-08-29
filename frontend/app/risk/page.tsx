import { TiltCard } from "@/components/ui/TiltCard";

export default function Page() {
  return (
    <div className="space-y-6">
      <h2 className="aurora text-3xl font-black">ریسک</h2>
      <div className="grid gap-4 md:grid-cols-2">
        <TiltCard>
          <p className="text-xs text-slate-400">هر معامله</p>
          <p className="mt-2 text-2xl font-semibold">۰.۵٪</p>
        </TiltCard>
        <TiltCard>
          <p className="text-xs text-slate-400">سقف ضرر روزانه</p>
          <p className="mt-2 text-2xl font-semibold">۲٪</p>
        </TiltCard>
      </div>
    </div>
  );
}
