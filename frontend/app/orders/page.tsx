import { TiltCard } from "@/components/ui/TiltCard";

export default function Page() {
  return (
    <div className="space-y-6">
      <h2 className="aurora text-3xl font-black">سفارش‌ها</h2>
      <TiltCard>
        <p className="text-slate-300">دفتر سفارش خالی است تا اولین فیل زنده.</p>
      </TiltCard>
    </div>
  );
}
