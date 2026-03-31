"use client";

import { useState, useEffect } from "react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

interface SparklineProps {
  data: { time: string; value: number }[];
  color?: string;
  height?: number;
  showAxis?: boolean;
  showTooltip?: boolean;
  gradientId?: string;
}

export function Sparkline({
  data,
  color = "#22d3ee",
  height = 60,
  showAxis = false,
  showTooltip = true,
  gradientId = "sparkGradient",
}: SparklineProps) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted) return <div style={{ width: "100%", height }} />;

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.3} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        {showAxis && (
          <>
            <XAxis dataKey="time" hide />
            <YAxis hide domain={["dataMin", "dataMax"]} />
          </>
        )}
        {showTooltip && (
          <Tooltip
            contentStyle={{
              background: "rgba(15,17,23,0.95)",
              border: "1px solid rgba(255,255,255,0.08)",
              borderRadius: "12px",
              fontSize: "12px",
              color: "#e2e8f0",
            }}
            labelStyle={{ color: "#94a3b8" }}
          />
        )}
        <Area
          type="monotone"
          dataKey="value"
          stroke={color}
          strokeWidth={2}
          fill={`url(#${gradientId})`}
          dot={false}
          animationDuration={1000}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
