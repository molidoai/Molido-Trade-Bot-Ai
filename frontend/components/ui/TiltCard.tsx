"use client";

import { useRef } from "react";

export function TiltCard({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);

  const onMove = (e: React.MouseEvent) => {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width - 0.5;
    const y = (e.clientY - r.top) / r.height - 0.5;
    el.style.transform = `rotateY(${x * -12}deg) rotateX(${y * 10}deg) translateZ(12px)`;
  };

  const onLeave = () => {
    const el = ref.current;
    if (!el) return;
    el.style.transform = "rotateY(0deg) rotateX(0deg) translateZ(0)";
  };

  return (
    <div style={{ perspective: 900 }} className={className}>
      <div
        ref={ref}
        onMouseMove={onMove}
        onMouseLeave={onLeave}
        className="glass h-full rounded-2xl p-5 transition-transform duration-200 ease-out will-change-transform"
      >
        {children}
      </div>
    </div>
  );
}
