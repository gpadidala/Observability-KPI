"use client";

import { useState, useEffect, useMemo } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { useReportData } from "@/lib/use-report-data";
import {
  DollarSign,
  TrendingUp,
  HardDrive,
  Lightbulb,
  Settings,
} from "lucide-react";
import {
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

import { GlassCard } from "@/components/glass-card";
import {
  cn,
  formatCurrency,
  pillarColor,
} from "@/lib/utils";
import { PILLARS, type ReportResponse } from "@/lib/api";

/* -------------------------------------------------------------------------- */
/*  Demo data                                                                 */
/* -------------------------------------------------------------------------- */

interface CostRow {
  pillar: string;
  label: string;
  monthlyCost: number;
  gbIngested: number | null;
  costPerGB: number | null;
  percentOfTotal: number;
  color: string;
}

function generateDemoCostData(): {
  rows: CostRow[];
  totalCost: number;
  totalVolume: number;
  costPerGB: number;
  report: ReportResponse;
} {
  const rows: CostRow[] = [
    {
      pillar: "mimir",
      label: "Mimir",
      monthlyCost: 15_000,
      gbIngested: 45.2,
      costPerGB: 331.86,
      percentOfTotal: 45.5,
      color: pillarColor("mimir"),
    },
    {
      pillar: "loki",
      label: "Loki",
      monthlyCost: 8_000,
      gbIngested: 128.5,
      costPerGB: 62.26,
      percentOfTotal: 24.2,
      color: pillarColor("loki"),
    },
    {
      pillar: "tempo",
      label: "Tempo",
      monthlyCost: 5_000,
      gbIngested: 23.1,
      costPerGB: 216.45,
      percentOfTotal: 15.2,
      color: pillarColor("tempo"),
    },
    {
      pillar: "pyroscope",
      label: "Pyroscope",
      monthlyCost: 2_000,
      gbIngested: 8.7,
      costPerGB: 229.89,
      percentOfTotal: 6.1,
      color: pillarColor("pyroscope"),
    },
    {
      pillar: "grafana",
      label: "Grafana",
      monthlyCost: 3_000,
      gbIngested: null,
      costPerGB: null,
      percentOfTotal: 9.1,
      color: pillarColor("grafana"),
    },
  ];

  const totalCost = rows.reduce((s, r) => s + r.monthlyCost, 0);
  const totalVolume = rows.reduce((s, r) => s + (r.gbIngested ?? 0), 0);
  const costPerGB = totalCost / totalVolume;

  /* Minimal ReportResponse for typing compliance */
  const report: ReportResponse = {
    environment: "PROD",
    time_range: { start: "2026-03-01T00:00:00Z", end: "2026-03-30T23:59:59Z" },
    effective_query_windows: [],
    kpis: PILLARS.map((p) => ({
      pillar: p.key,
      kpis: [
        {
          kpi_name: "Monthly Cost",
          value: rows.find((r) => r.pillar === p.key)?.monthlyCost ?? 0,
          unit: "USD",
          pillar: p.key,
          environment: "PROD",
          time_windows: [],
          details: {},
        },
      ],
    })),
    generated_at: new Date().toISOString(),
  };

  return { rows, totalCost, totalVolume, costPerGB, report };
}

/* -------------------------------------------------------------------------- */
/*  Recommendations                                                           */
/* -------------------------------------------------------------------------- */

interface Recommendation {
  id: number;
  title: string;
  description: string;
  impact: "High" | "Medium" | "Low";
}

const RECOMMENDATIONS: Recommendation[] = [
  {
    id: 1,
    title: "Review Mimir retention policies",
    description:
      "Mimir accounts for 45.5% of total cost. Reducing retention from 90 to 30 days for non-critical metrics could save up to $5,000/mo.",
    impact: "High",
  },
  {
    id: 2,
    title: "Implement Loki log sampling for non-critical namespaces",
    description:
      "Loki ingests 128.5 GB but has the lowest cost-per-GB. Sampling debug/info logs at 10% for staging namespaces can reduce volume by 40%.",
    impact: "High",
  },
  {
    id: 3,
    title: "Enable Tempo tail-based sampling",
    description:
      "Switch from head-based to tail-based sampling to retain only traces with errors or high latency, reducing storage by ~35%.",
    impact: "Medium",
  },
  {
    id: 4,
    title: "Consolidate Pyroscope profiling targets",
    description:
      "Several profiling targets overlap with Mimir resource metrics. Consolidating to critical services only can reduce Pyroscope costs.",
    impact: "Low",
  },
];

/* -------------------------------------------------------------------------- */
/*  Tooltip components                                                        */
/* -------------------------------------------------------------------------- */

function GlassTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-white/[0.08] bg-[#0f1117]/95 px-4 py-3 shadow-xl backdrop-blur-xl">
      <p className="mb-1 text-xs text-slate-400">{label}</p>
      {payload.map((entry: any) => (
        <p key={entry.dataKey} className="text-sm font-medium" style={{ color: entry.color ?? entry.fill }}>
          {entry.name}: {typeof entry.value === "number" ? formatCurrency(entry.value) : entry.value}
        </p>
      ))}
    </div>
  );
}

function PieTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0];
  return (
    <div className="rounded-xl border border-white/[0.08] bg-[#0f1117]/95 px-4 py-3 shadow-xl backdrop-blur-xl">
      <p className="text-sm font-medium" style={{ color: d.payload.fill }}>
        {d.name}: {formatCurrency(d.value)} ({d.payload.percentOfTotal}%)
      </p>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Impact badge                                                              */
/* -------------------------------------------------------------------------- */

function ImpactBadge({ impact }: { impact: string }) {
  const styles: Record<string, string> = {
    High: "bg-red-400/10 text-red-400 ring-red-400/20",
    Medium: "bg-yellow-400/10 text-yellow-400 ring-yellow-400/20",
    Low: "bg-slate-400/10 text-slate-400 ring-slate-400/20",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-medium ring-1 ring-inset",
        styles[impact] ?? styles.Low,
      )}
    >
      {impact} Impact
    </span>
  );
}

/* -------------------------------------------------------------------------- */
/*  Pie chart label renderer                                                  */
/* -------------------------------------------------------------------------- */

function renderPieLabel({
  cx,
  cy,
  midAngle,
  innerRadius,
  outerRadius,
  percent,
}: any) {
  const RADIAN = Math.PI / 180;
  const radius = innerRadius + (outerRadius - innerRadius) * 1.4;
  const x = cx + radius * Math.cos(-midAngle * RADIAN);
  const y = cy + radius * Math.sin(-midAngle * RADIAN);
  return (
    <text
      x={x}
      y={y}
      fill="#94a3b8"
      textAnchor={x > cx ? "start" : "end"}
      dominantBaseline="central"
      fontSize={12}
    >
      {`${(percent * 100).toFixed(1)}%`}
    </text>
  );
}

/* -------------------------------------------------------------------------- */
/*  SSR hydration guard                                                       */
/* -------------------------------------------------------------------------- */

function useIsClient() {
  const [isClient, setIsClient] = useState(false);
  useEffect(() => setIsClient(true), []);
  return isClient;
}

/* -------------------------------------------------------------------------- */
/*  Page                                                                      */
/* -------------------------------------------------------------------------- */

export default function CostEfficiencyPage() {
  const isClient = useIsClient();
  const { report, isLoading } = useReportData();

  /* Transform report data into cost rows if available */
  const data = useMemo(() => {
    if (!report) return null;

    /* Try to extract cost KPIs from report; fall back to generateDemoCostData structure */
    const rows: CostRow[] = PILLARS.map((p) => {
      const pillarMatch = report.kpis.find(
        (pk) => pk.pillar.toLowerCase() === p.key.toLowerCase() || pk.pillar.toLowerCase() === p.label.toLowerCase(),
      );
      const kpis = pillarMatch?.kpis ?? [];
      const costKpi = kpis.find((k) => k.kpi_name.toLowerCase().includes("monthly cost") || k.kpi_name.toLowerCase().includes("cost split"));
      const costGBKpi = kpis.find((k) => k.kpi_name.toLowerCase().includes("cost per gb"));
      const ingestKpi = kpis.find((k) => k.kpi_name.toLowerCase().includes("ingest"));
      const monthlyCost = costKpi?.value ?? 0;
      const gbIngested = ingestKpi ? (ingestKpi.unit === "bytes" ? ingestKpi.value / 1e9 : ingestKpi.value) : null;
      const costPerGB = costGBKpi?.value ?? (gbIngested && gbIngested > 0 ? monthlyCost / gbIngested : null);
      return {
        pillar: p.key,
        label: p.label,
        monthlyCost,
        gbIngested: p.key === "grafana" ? null : gbIngested,
        costPerGB: p.key === "grafana" ? null : costPerGB,
        percentOfTotal: 0,
        color: pillarColor(p.key),
      };
    });
    const totalCost = rows.reduce((s, r) => s + r.monthlyCost, 0);
    rows.forEach((r) => { r.percentOfTotal = totalCost > 0 ? (r.monthlyCost / totalCost) * 100 : 0; });
    const totalVolume = rows.reduce((s, r) => s + (r.gbIngested ?? 0), 0);
    const costPerGB = totalVolume > 0 ? totalCost / totalVolume : 0;
    return { rows, totalCost, totalVolume, costPerGB, report };
  }, [report]);

  if (isLoading || !isClient) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <GlassCard className="max-w-md text-center" glow="purple">
          <Settings className="mx-auto mb-4 h-10 w-10 text-slate-500" />
          <h2 className="mb-2 text-lg font-semibold text-slate-200">No Cost Data Available</h2>
          <p className="text-sm text-slate-400">
            Configure your Grafana connection and generate a report in{" "}
            <Link href="/settings" className="text-indigo-400 underline underline-offset-2 hover:text-indigo-300">
              Settings
            </Link>{" "}
            to view cost analysis.
          </p>
        </GlassCard>
      </div>
    );
  }

  const barChartData = data.rows.map((r) => ({
    name: r.label,
    cost: r.monthlyCost,
    fill: r.color,
  }));

  const pieChartData = data.rows.map((r) => ({
    name: r.label,
    value: r.monthlyCost,
    fill: r.color,
    percentOfTotal: r.percentOfTotal,
  }));

  return (
    <div className="space-y-6">
      {/* ------------------------------------------------------------------ */}
      {/*  Page header                                                       */}
      {/* ------------------------------------------------------------------ */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="flex items-center gap-3"
      >
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-500/15">
          <DollarSign className="h-5 w-5 text-cyan-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-100">
            Cost & Efficiency
          </h1>
          <p className="text-sm text-slate-400">
            Infrastructure spend analysis and optimization
          </p>
        </div>
      </motion.div>

      {/* ------------------------------------------------------------------ */}
      {/*  Hero stat cards                                                   */}
      {/* ------------------------------------------------------------------ */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {/* Total Monthly Cost */}
        <GlassCard glow="cyan" delay={0.05}>
          <div className="flex items-center justify-between">
            <p className="text-[10px] uppercase tracking-wider text-slate-500">
              Total Monthly Cost
            </p>
            <TrendingUp className="h-4 w-4 text-cyan-400" />
          </div>
          <p className="mt-2 text-3xl font-bold tabular-nums text-cyan-400">
            {formatCurrency(data.totalCost)}
          </p>
          <p className="mt-1 text-xs text-slate-500">Across all pillars</p>
        </GlassCard>

        {/* Cost per GB */}
        <GlassCard glow="purple" delay={0.1}>
          <div className="flex items-center justify-between">
            <p className="text-[10px] uppercase tracking-wider text-slate-500">
              Cost per GB
            </p>
            <DollarSign className="h-4 w-4 text-purple-400" />
          </div>
          <p className="mt-2 text-3xl font-bold tabular-nums text-purple-400">
            ${data.costPerGB.toFixed(2)}
          </p>
          <p className="mt-1 text-xs text-slate-500">Weighted average</p>
        </GlassCard>

        {/* Total Volume Ingested */}
        <GlassCard glow="green" delay={0.15}>
          <div className="flex items-center justify-between">
            <p className="text-[10px] uppercase tracking-wider text-slate-500">
              Total Volume Ingested
            </p>
            <HardDrive className="h-4 w-4 text-emerald-400" />
          </div>
          <p className="mt-2 text-3xl font-bold tabular-nums text-emerald-400">
            {data.totalVolume.toFixed(1)} GB
          </p>
          <p className="mt-1 text-xs text-slate-500">30-day period</p>
        </GlassCard>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/*  Cost Breakdown Table                                              */}
      {/* ------------------------------------------------------------------ */}
      <GlassCard delay={0.2}>
        <h3 className="mb-4 text-sm font-semibold text-slate-200">
          Pillar Cost Breakdown
        </h3>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/[0.06]">
                {["Pillar", "Monthly Cost", "GB Ingested", "Cost / GB", "% of Total"].map(
                  (h) => (
                    <th
                      key={h}
                      className="px-4 py-2.5 text-left text-[10px] font-semibold uppercase tracking-wider text-slate-500"
                    >
                      {h}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row) => (
                <tr
                  key={row.pillar}
                  className="border-b border-white/[0.03] transition-colors hover:bg-white/[0.02]"
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2.5">
                      <span
                        className="h-2.5 w-2.5 rounded-full"
                        style={{ backgroundColor: row.color }}
                      />
                      <span className="font-medium text-slate-200">
                        {row.label}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3 font-medium text-slate-200">
                    {formatCurrency(row.monthlyCost)}
                  </td>
                  <td className="px-4 py-3 text-slate-300">
                    {row.gbIngested !== null
                      ? `${row.gbIngested} GB`
                      : <span className="text-slate-500">&mdash;</span>}
                  </td>
                  <td className="px-4 py-3 text-slate-300">
                    {row.costPerGB !== null
                      ? `$${row.costPerGB.toFixed(2)}`
                      : <span className="text-slate-500">&mdash;</span>}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-white/[0.06]">
                        <div
                          className="h-full rounded-full transition-all duration-500"
                          style={{
                            width: `${row.percentOfTotal}%`,
                            backgroundColor: row.color,
                          }}
                        />
                      </div>
                      <span className="text-xs font-medium text-slate-300">
                        {row.percentOfTotal}%
                      </span>
                    </div>
                  </td>
                </tr>
              ))}

              {/* Total row */}
              <tr className="border-t border-white/[0.08] bg-white/[0.02]">
                <td className="px-4 py-3 font-bold text-slate-100">Total</td>
                <td className="px-4 py-3 font-bold text-slate-100">
                  {formatCurrency(data.totalCost)}
                </td>
                <td className="px-4 py-3 font-bold text-slate-100">
                  {data.totalVolume.toFixed(1)} GB
                </td>
                <td className="px-4 py-3 font-bold text-slate-100">
                  ${data.costPerGB.toFixed(2)}
                </td>
                <td className="px-4 py-3 font-bold text-slate-100">100%</td>
              </tr>
            </tbody>
          </table>
        </div>
      </GlassCard>

      {/* ------------------------------------------------------------------ */}
      {/*  Charts                                                            */}
      {/* ------------------------------------------------------------------ */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Bar chart */}
        <GlassCard delay={0.25}>
          <h3 className="mb-4 text-sm font-semibold text-slate-200">
            Cost by Pillar
          </h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={barChartData} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
              <XAxis
                dataKey="name"
                tick={{ fill: "#64748b", fontSize: 12 }}
                axisLine={{ stroke: "rgba(255,255,255,0.06)" }}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: "#64748b", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`}
              />
              <Tooltip content={<GlassTooltip />} />
              <Bar
                dataKey="cost"
                name="Monthly Cost"
                radius={[6, 6, 0, 0]}
                animationDuration={1000}
              >
                {barChartData.map((entry, index) => (
                  <Cell key={index} fill={entry.fill} fillOpacity={0.85} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </GlassCard>

        {/* Pie / Donut chart */}
        <GlassCard delay={0.3}>
          <h3 className="mb-4 text-sm font-semibold text-slate-200">
            Cost Distribution
          </h3>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={pieChartData}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={100}
                dataKey="value"
                nameKey="name"
                label={renderPieLabel}
                animationDuration={1000}
                stroke="rgba(15,17,23,0.8)"
                strokeWidth={2}
              >
                {pieChartData.map((entry, index) => (
                  <Cell key={index} fill={entry.fill} />
                ))}
              </Pie>
              <Tooltip content={<PieTooltip />} />
              <Legend
                wrapperStyle={{ paddingTop: 12, fontSize: 12, color: "#94a3b8" }}
              />
            </PieChart>
          </ResponsiveContainer>
        </GlassCard>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/*  Optimization Recommendations                                      */}
      {/* ------------------------------------------------------------------ */}
      <GlassCard delay={0.35}>
        <div className="mb-4 flex items-center gap-2">
          <Lightbulb className="h-4 w-4 text-yellow-400" />
          <h3 className="text-sm font-semibold text-slate-200">
            Optimization Recommendations
          </h3>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {RECOMMENDATIONS.map((rec) => (
            <motion.div
              key={rec.id}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35, delay: 0.4 + rec.id * 0.08 }}
              className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4"
            >
              <div className="mb-2 flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-indigo-500/15 text-xs font-bold text-indigo-300">
                    {rec.id}
                  </span>
                  <h4 className="text-sm font-medium text-slate-200">
                    {rec.title}
                  </h4>
                </div>
                <ImpactBadge impact={rec.impact} />
              </div>
              <p className="ml-10 text-xs leading-relaxed text-slate-400">
                {rec.description}
              </p>
            </motion.div>
          ))}
        </div>
      </GlassCard>
    </div>
  );
}
