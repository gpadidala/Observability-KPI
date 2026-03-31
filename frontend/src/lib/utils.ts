import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatNumber(n: number, decimals = 2): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toFixed(decimals);
}

export function formatPercent(n: number, decimals = 2): string {
  return `${n.toFixed(decimals)}%`;
}

export function formatCurrency(n: number): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);
}

export function formatBytes(bytes: number): string {
  if (bytes >= 1e12) return `${(bytes / 1e12).toFixed(1)} TB`;
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`;
  if (bytes >= 1e6) return `${(bytes / 1e6).toFixed(1)} MB`;
  if (bytes >= 1e3) return `${(bytes / 1e3).toFixed(1)} KB`;
  return `${bytes} B`;
}

export function formatDateRange(start: string, end: string): string {
  const s = new Date(start);
  const e = new Date(end);
  const opts: Intl.DateTimeFormatOptions = { month: "short", day: "numeric", year: "numeric" };
  return `${s.toLocaleDateString("en-US", opts)} — ${e.toLocaleDateString("en-US", opts)}`;
}

export function kpiStatusColor(kpiName: string, value: number): string {
  if (kpiName.toLowerCase().includes("loss") || kpiName.toLowerCase().includes("drop")) {
    if (value < 0.1) return "text-emerald-400";
    if (value < 1.0) return "text-yellow-400";
    return "text-red-400";
  }
  if (kpiName.toLowerCase().includes("uptime") || kpiName.toLowerCase().includes("availability")) {
    if (value >= 99.9) return "text-emerald-400";
    if (value >= 99.0) return "text-yellow-400";
    return "text-red-400";
  }
  if (kpiName.toLowerCase().includes("cpu") || kpiName.toLowerCase().includes("memory")) {
    if (value < 70) return "text-emerald-400";
    if (value < 85) return "text-yellow-400";
    return "text-red-400";
  }
  return "text-cyan-400";
}

export function kpiGlowColor(kpiName: string, value: number): "cyan" | "green" | "red" | "purple" | "none" {
  if (kpiName.toLowerCase().includes("loss")) {
    if (value < 0.1) return "green";
    if (value < 1.0) return "cyan";
    return "red";
  }
  if (kpiName.toLowerCase().includes("uptime") || kpiName.toLowerCase().includes("availability")) {
    if (value >= 99.9) return "green";
    if (value >= 99.0) return "cyan";
    return "red";
  }
  return "cyan";
}

export function pillarColor(pillar: string): string {
  switch (pillar.toLowerCase()) {
    case "mimir": return "#22d3ee";
    case "loki": return "#a855f7";
    case "tempo": return "#34d399";
    case "pyroscope": return "#fb923c";
    case "grafana": return "#6366f1";
    default: return "#64748b";
  }
}

export function pillarIcon(pillar: string): string {
  switch (pillar.toLowerCase()) {
    case "mimir": return "BarChart3";
    case "loki": return "FileText";
    case "tempo": return "GitBranch";
    case "pyroscope": return "Flame";
    case "grafana": return "Monitor";
    default: return "Database";
  }
}
