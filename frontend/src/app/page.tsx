"use client";

import { useMemo, useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { useReportData, aggregateKpi } from "@/lib/use-report-data";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BarChart3,
  CalendarRange,
  Clock,
  Cpu,
  DollarSign,
  HardDrive,
  Layers,
  Shield,
  TrendingDown,
  Zap,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { GlassCard } from "@/components/glass-card";
import { MetricGauge } from "@/components/metric-gauge";
import {
  cn,
  formatPercent,
  formatCurrency,
  formatDateRange,
  kpiStatusColor,
  pillarColor,
} from "@/lib/utils";
import { type KPIResult } from "@/lib/api";

/* -------------------------------------------------------------------------- */
/*  Helpers                                                                   */
/* -------------------------------------------------------------------------- */

function kpiValue(pillarKpis: KPIResult[], nameFragment: string): number {
  const match = pillarKpis.find((k) =>
    k.kpi_name.toLowerCase().includes(nameFragment.toLowerCase()),
  );
  return match?.value ?? 0;
}

function CostTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="glass-strong rounded-xl px-4 py-3 text-sm shadow-xl">
      <p className="mb-1 font-medium text-slate-200">{label}</p>
      <p className="tabular-nums text-cyan-400">{formatCurrency(payload[0].value)}</p>
    </div>
  );
}

const recentActivity = [
  { id: 1, action: "Report generated", detail: "PERF environment — 30-day window", severity: "info" as const, time: "2 min ago" },
  { id: 2, action: "Threshold alert", detail: "Pyroscope availability dropped below 99.8%", severity: "warning" as const, time: "18 min ago" },
  { id: 3, action: "Connection validated", detail: "Grafana v11.4.0 — all datasources healthy", severity: "success" as const, time: "1 hr ago" },
  { id: 4, action: "Cost spike detected", detail: "Mimir ingest rate +12% over rolling average", severity: "warning" as const, time: "3 hr ago" },
  { id: 5, action: "PDF export completed", detail: "Leadership summary — Q1 2026", severity: "info" as const, time: "5 hr ago" },
];

const severityStyles: Record<string, string> = {
  info: "bg-cyan-500/15 text-cyan-400 ring-cyan-500/30",
  warning: "bg-amber-500/15 text-amber-400 ring-amber-500/30",
  success: "bg-emerald-500/15 text-emerald-400 ring-emerald-500/30",
  error: "bg-red-500/15 text-red-400 ring-red-500/30",
};

/* -------------------------------------------------------------------------- */
/*  Page Component                                                            */
/* -------------------------------------------------------------------------- */

export default function DashboardPage() {
  /* ---- All hooks MUST be called unconditionally at the top ---- */
  const [isClient, setIsClient] = useState(false);
  useEffect(() => setIsClient(true), []);

  const { report, isLoading } = useReportData();

  const platformAvailability = report ? aggregateKpi(report, "availability", "avg") : 0;
  const dataLossRate = report ? aggregateKpi(report, "loss", "avg") : 0;
  const totalMonthlyCost = report ? aggregateKpi(report, "monthly cost", "sum") : 0;
  const peakCpu = report ? aggregateKpi(report, "cpu", "max") : 0;
  const peakMemory = report ? aggregateKpi(report, "memory", "max") : 0;
  const avgCostPerGB = report ? aggregateKpi(report, "cost per gb", "avg") : 0;

  const costChartData = useMemo(() => {
    if (!report) return [];
    return report.kpis.map((p) => ({
      name: p.pillar,
      cost: kpiValue(p.kpis, "monthly cost"),
      color: pillarColor(p.pillar),
    }));
  }, [report]);

  /* ---- Loading / SSR guard ---- */
  if (!isClient || isLoading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
      </div>
    );
  }

  /* ---- Empty state ---- */
  if (!report) {
    return (
      <div className="mx-auto max-w-5xl space-y-8">
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="flex items-center gap-4"
        >
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-cyan-400 shadow-lg shadow-indigo-500/25">
            <Layers className="h-6 w-6 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-100">Executive Summary</h1>
            <p className="text-sm text-slate-500">Real-time observability KPI overview</p>
          </div>
        </motion.div>

        <GlassCard glow="purple" delay={0.15}>
          <div className="flex flex-col items-center gap-5 py-12 text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-indigo-500/15">
              <AlertTriangle className="h-8 w-8 text-indigo-400" />
            </div>
            <div className="space-y-2">
              <h2 className="text-xl font-semibold text-slate-100">No Report Data Available</h2>
              <p className="max-w-md text-sm text-slate-400">
                Configure your Grafana connection in Settings to generate a report. Once configured, KPI data will appear here automatically.
              </p>
            </div>
            <Link
              href="/settings"
              className="mt-2 inline-flex items-center gap-2 rounded-xl bg-indigo-500/20 px-5 py-2.5 text-sm font-medium text-indigo-300 ring-1 ring-inset ring-indigo-500/30 transition-all hover:bg-indigo-500/30 hover:shadow-[0_0_20px_rgba(99,102,241,0.2)]"
            >
              Go to Settings
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </GlassCard>
      </div>
    );
  }

  /* ---- Loaded state ---- */
  return (
    <div className="mx-auto max-w-7xl space-y-6">
      {/* Page Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="flex items-center gap-4"
      >
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-cyan-400 shadow-lg shadow-indigo-500/25">
          <Layers className="h-6 w-6 text-white" />
        </div>
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-100">Executive Summary</h1>
          <p className="text-sm text-slate-500">Real-time observability KPI overview</p>
        </div>
        <span className="ml-auto rounded-full bg-emerald-500/15 px-3 py-1 text-xs font-medium text-emerald-400 ring-1 ring-inset ring-emerald-500/25">
          {report.environment}
        </span>
      </motion.div>

      {/* Hero Stats Row */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <GlassCard glow="cyan" delay={0.05}>
          <div className="flex items-start justify-between">
            <div className="space-y-1">
              <p className="text-xs font-medium uppercase tracking-wider text-slate-500">Platform Availability</p>
              <p className={cn("text-3xl font-bold tabular-nums", kpiStatusColor("availability", platformAvailability))}>
                {formatPercent(platformAvailability, 2)}
              </p>
              <p className="text-xs text-slate-500">Across all pillars</p>
            </div>
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-cyan-500/10">
              <Shield className="h-7 w-7 text-cyan-400" />
            </div>
          </div>
        </GlassCard>

        <GlassCard glow="green" delay={0.1}>
          <div className="flex items-start justify-between">
            <div className="space-y-1">
              <p className="text-xs font-medium uppercase tracking-wider text-slate-500">Data Loss Rate</p>
              <p className={cn("text-3xl font-bold tabular-nums", kpiStatusColor("loss", dataLossRate))}>
                {formatPercent(dataLossRate, 3)}
              </p>
              <p className="text-xs text-slate-500">Platform-wide</p>
            </div>
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-500/10">
              <TrendingDown className="h-7 w-7 text-emerald-400" />
            </div>
          </div>
        </GlassCard>

        <GlassCard glow="purple" delay={0.15}>
          <div className="flex items-start justify-between">
            <div className="space-y-1">
              <p className="text-xs font-medium uppercase tracking-wider text-slate-500">Total Monthly Cost</p>
              <p className="text-3xl font-bold tabular-nums text-purple-400">{formatCurrency(totalMonthlyCost)}</p>
              <p className="text-xs text-slate-500">Infrastructure spend</p>
            </div>
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-purple-500/10">
              <DollarSign className="h-7 w-7 text-purple-400" />
            </div>
          </div>
        </GlassCard>
      </div>

      {/* KPI Gauges */}
      <GlassCard delay={0.2}>
        <div className="mb-5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Activity className="h-5 w-5 text-indigo-400" />
            <h2 className="text-base font-semibold text-slate-100">Key Performance Indicators</h2>
          </div>
          <div className="flex items-center gap-2 rounded-full bg-emerald-500/10 px-3 py-1">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
            </span>
            <span className="text-xs font-medium text-emerald-400">Live</span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-8 sm:grid-cols-3 lg:grid-cols-5">
          <MetricGauge label="Availability" value={platformAvailability} unit="%" thresholds={{ warning: 99.9, critical: 99.0 }} invertThresholds icon={<Shield className="h-4 w-4" />} subtitle="Uptime" />
          <MetricGauge label="Data Loss Rate" value={dataLossRate} unit="%" thresholds={{ warning: 0.1, critical: 1.0 }} icon={<TrendingDown className="h-4 w-4" />} subtitle="Platform-wide" />
          <MetricGauge label="Peak CPU" value={peakCpu} unit="%" thresholds={{ warning: 70, critical: 85 }} icon={<Cpu className="h-4 w-4" />} subtitle="Max utilization" />
          <MetricGauge label="Peak Memory" value={peakMemory} unit="%" thresholds={{ warning: 70, critical: 85 }} icon={<HardDrive className="h-4 w-4" />} subtitle="Max utilization" />
          <div className="flex flex-col items-center gap-2">
            <div className="relative flex h-28 w-28 flex-col items-center justify-center rounded-full border-[6px] border-white/[0.06]">
              <DollarSign className="mb-0.5 h-4 w-4 text-slate-400" />
              <span className="text-xl font-bold tabular-nums text-cyan-400">${avgCostPerGB.toFixed(2)}</span>
              <span className="text-[10px] uppercase tracking-wider text-slate-500">$/GB</span>
            </div>
            <div className="text-center">
              <p className="text-sm font-medium text-slate-200">Cost per GB</p>
              <p className="text-[11px] text-slate-500">Avg ingest cost</p>
            </div>
          </div>
        </div>
      </GlassCard>

      {/* Cost Distribution */}
      <GlassCard delay={0.25}>
        <div className="mb-5 flex items-center gap-3">
          <BarChart3 className="h-5 w-5 text-indigo-400" />
          <h2 className="text-base font-semibold text-slate-100">Cost Breakdown by Pillar</h2>
        </div>
        <div className="h-[280px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={costChartData} margin={{ top: 8, right: 8, bottom: 8, left: 8 }} barSize={48}>
              <CartesianGrid strokeDasharray="3 6" stroke="rgba(255,255,255,0.04)" vertical={false} />
              <XAxis dataKey="name" tick={{ fill: "#94a3b8", fontSize: 12 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}K`} />
              <Tooltip content={<CostTooltip />} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
              <Bar dataKey="cost" radius={[8, 8, 0, 0]}>
                {costChartData.map((entry, i) => (
                  <Cell key={i} fill={entry.color} fillOpacity={0.75} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {costChartData.map((entry) => (
            <div key={entry.name} className="flex items-center gap-3 rounded-xl bg-white/[0.03] px-3 py-2.5">
              <span className="h-3 w-3 shrink-0 rounded-full" style={{ backgroundColor: entry.color }} />
              <div className="min-w-0">
                <p className="truncate text-xs text-slate-400">{entry.name}</p>
                <p className="text-sm font-semibold tabular-nums text-slate-200">{formatCurrency(entry.cost)}</p>
              </div>
            </div>
          ))}
        </div>
      </GlassCard>

      {/* Query Transparency */}
      <GlassCard delay={0.3}>
        <div className="mb-5 flex items-center gap-3">
          <CalendarRange className="h-5 w-5 text-indigo-400" />
          <h2 className="text-base font-semibold text-slate-100">Effective Query Windows</h2>
        </div>
        <div className="mb-4 flex flex-wrap items-center gap-4 text-sm">
          <span className="text-slate-400">
            Time Range:{" "}
            <span className="font-medium text-slate-200">
              {formatDateRange(report.time_range.start, report.time_range.end)}
            </span>
          </span>
          <span className="rounded-full bg-indigo-500/15 px-2.5 py-0.5 text-xs font-medium text-indigo-300 ring-1 ring-inset ring-indigo-500/25">
            {report.effective_query_windows.length} window{report.effective_query_windows.length !== 1 ? "s" : ""}
          </span>
        </div>
        <div className="flex flex-wrap gap-2">
          {report.effective_query_windows.map((w, i) => {
            const s = new Date(w.start);
            const e = new Date(w.end);
            const fmt = (d: Date) => d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
            return (
              <motion.div
                key={i}
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.3, delay: 0.35 + i * 0.05 }}
                className="inline-flex items-center gap-2 rounded-full bg-white/[0.04] px-4 py-2 text-xs ring-1 ring-inset ring-white/[0.06]"
              >
                <Clock className="h-3 w-3 text-slate-500" />
                <span className="font-medium text-slate-300">{fmt(s)}</span>
                <ArrowRight className="h-3 w-3 text-slate-600" />
                <span className="font-medium text-slate-300">{fmt(e)}</span>
              </motion.div>
            );
          })}
        </div>
      </GlassCard>

      {/* Recent Activity */}
      <GlassCard delay={0.35}>
        <div className="mb-5 flex items-center gap-3">
          <Zap className="h-5 w-5 text-indigo-400" />
          <h2 className="text-base font-semibold text-slate-100">Recent Activity</h2>
        </div>
        <div className="space-y-2">
          {recentActivity.map((item, i) => (
            <motion.div
              key={item.id}
              initial={{ opacity: 0, x: -12 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.3, delay: 0.4 + i * 0.06 }}
              className="flex items-center gap-4 rounded-xl bg-white/[0.02] px-4 py-3 transition-colors hover:bg-white/[0.04]"
            >
              <span className={cn("shrink-0 rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ring-1 ring-inset", severityStyles[item.severity])}>
                {item.severity}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-slate-200">{item.action}</p>
                <p className="truncate text-xs text-slate-500">{item.detail}</p>
              </div>
              <span className="shrink-0 text-xs text-slate-600">{item.time}</span>
            </motion.div>
          ))}
        </div>
      </GlassCard>
    </div>
  );
}
