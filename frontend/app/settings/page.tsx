import { TiltCard } from "@/components/ui/TiltCard";

export default function Page() {
  return (
    <div className="space-y-6">
      <h2 className="aurora text-3xl font-black">تنظیمات</h2>
      <TiltCard>
        <p className="text-sm text-slate-300">حالت: REAL · مستر: ON. مقادیر واقعی در فایل .env روی سرور است، نه داخل گیت.</p>
      </TiltCard>
    </div>
  );
}
