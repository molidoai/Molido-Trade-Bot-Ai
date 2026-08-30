"use client";

import { useEffect, useRef } from "react";

export function Scene3D() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let raf = 0;
    let t = 0;
    const particles = Array.from({ length: 90 }, () => ({
      x: Math.random() * 2 - 1,
      y: Math.random() * 2 - 1,
      z: Math.random() * 2,
      r: 0.5 + Math.random() * 2,
      gold: Math.random() > 0.55,
    }));

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = window.innerWidth * dpr;
      canvas.height = window.innerHeight * dpr;
    };
    resize();
    window.addEventListener("resize", resize);

    const loop = () => {
      t += 0.01;
      const w = canvas.width;
      const h = canvas.height;
      ctx.fillStyle = "rgba(4, 6, 18, 0.42)";
      ctx.fillRect(0, 0, w, h);

      const cx = w * 0.5;
      const cy = h * 0.44;

      const g = ctx.createRadialGradient(cx, cy, 20, cx, cy, w * 0.55);
      g.addColorStop(0, "rgba(8, 47, 73, 0.28)");
      g.addColorStop(0.45, "rgba(88, 28, 135, 0.08)");
      g.addColorStop(1, "rgba(4, 6, 18, 0)");
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, w, h);

      ctx.lineWidth = 1;
      for (let i = -14; i <= 14; i++) {
        ctx.beginPath();
        ctx.strokeStyle = `rgba(34, 211, 238, ${0.05 + Math.abs(Math.sin(t + i * 0.12)) * 0.1})`;
        for (let z = 0.35; z < 7.5; z += 0.18) {
          const zz = z + (t % 0.7);
          const persp = 240 / zz;
          const x = cx + i * persp * 1.2;
          const y = cy + (2.35 + Math.sin(t * 0.35) * 0.18) * persp;
          if (z <= 0.36) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
      }

      for (const p of particles) {
        p.z -= 0.014;
        if (p.z <= 0.06) {
          p.z = 2;
          p.x = Math.random() * 2 - 1;
          p.y = Math.random() * 2 - 1;
        }
        const persp = 340 / (p.z + 0.2);
        const x = cx + p.x * persp * 1.45;
        const y = cy + p.y * persp + Math.sin(t + p.x * 5) * 10;
        const a = Math.max(0, 1 - p.z / 2);
        ctx.fillStyle = p.gold
          ? `rgba(251, 191, 36, ${a * 0.75})`
          : `rgba(34, 211, 238, ${a * 0.8})`;
        ctx.beginPath();
        ctx.arc(x, y, p.r * (persp / 90), 0, Math.PI * 2);
        ctx.fill();
      }

      raf = requestAnimationFrame(loop);
    };

    ctx.fillStyle = "#040612";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    raf = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return <canvas ref={ref} className="pointer-events-none fixed inset-0 z-0 h-full w-full" />;
}
