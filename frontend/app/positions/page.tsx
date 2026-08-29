import { TiltCard } from "@/components/ui/TiltCard";

export default function Page() {
  return (
    <div className="space-y-6">
      <h2 className="aurora text-3xl font-black">پوزیشن‌ها</h2>
      <TiltCard>
        <p className="text-slate-300">پوزیشن بازی از بروکر خوانده می‌شود. هنوز تیکتی باز نیست.</p>
      </TiltCard>
    </div>
  );
}
