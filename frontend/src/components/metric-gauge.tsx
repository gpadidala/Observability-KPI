"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface MetricGaugeProps {
  label: string;
  value: number;
  unit?: string;
  thresholds?: { warning: number; critical: number };
  icon: React.ReactNode;
  subtitle?: string;
  invertThresholds?: boolean;
}

export function MetricGauge({
  label,
  value,
  unit = "%",
  thresholds,
  icon,
  subtitle,
  invertThresholds = false,
}: MetricGaugeProps) {
  const percent = Math.min(Math.max(value, 0), 100);

  const radius = 40;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset =
    circumference - (percent / 100) * circumference * 0.75;

  let arcColor = "#34d399";
  if (thresholds) {
    if (invertThresholds) {
      arcColor =
        value >= thresholds.warning
          ? "#34d399"
          : value >= thresholds.critical
            ? "#facc15"
            : "#f87171";
    } else {
      arcColor =
        value < thresholds.warning
          ? "#34d399"
          : value < thresholds.critical
            ? "#facc15"
            : "#f87171";
    }
  }

  const statusColor =
    arcColor === "#34d399"
      ? "text-emerald-400"
      : arcColor === "#facc15"
        ? "text-yellow-400"
        : "text-red-400";

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative h-28 w-28">
        <svg
          className="h-full w-full -rotate-[135deg]"
          viewBox="0 0 100 100"
        >
          <circle
            cx="50"
            cy="50"
            r={radius}
            fill="none"
            stroke="rgba(255,255,255,0.06)"
            strokeWidth="8"
            strokeDasharray={`${circumference * 0.75} ${circumference * 0.25}`}
            strokeLinecap="round"
          />
          <motion.circle
            cx="50"
            cy="50"
            r={radius}
            fill="none"
            stroke={arcColor}
            strokeWidth="8"
            strokeDasharray={`${circumference * 0.75} ${circumference * 0.25}`}
            strokeLinecap="round"
            initial={{ strokeDashoffset: circumference }}
            animate={{ strokeDashoffset }}
            transition={{ duration: 1.2, ease: "easeOut" }}
            style={{ filter: `drop-shadow(0 0 6px ${arcColor}40)` }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <div className="text-slate-400 mb-0.5">{icon}</div>
          <span
            className={cn("text-xl font-bold tabular-nums", statusColor)}
          >
            {value.toFixed(unit === "%" ? 1 : 2)}
          </span>
          <span className="text-[10px] text-slate-500 uppercase tracking-wider">
            {unit}
          </span>
        </div>
      </div>
      <div className="text-center">
        <p className="text-sm font-medium text-slate-200">{label}</p>
        {subtitle && (
          <p className="text-[11px] text-slate-500">{subtitle}</p>
        )}
      </div>
    </div>
  );
}
