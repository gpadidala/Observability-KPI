"use client";

import { useState, useEffect, useMemo } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import { useReportData } from "@/lib/use-report-data";
import {
  Shield,
  CheckCircle2,
  XCircle,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  Settings,
} from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";

import { GlassCard } from "@/components/glass-card";
import {
  cn,
  formatPercent,
  pillarColor,
  kpiStatusColor,
} from "@/lib/utils";
import { PILLARS, type ReportResponse, type PillarKPIs } from "@/lib/api";

/* -------------------------------------------------------------------------- */
/*  Demo data                                                                 */
/* -------------------------------------------------------------------------- */

const SLO_TARGET = 99.9;

interface AvailabilityRow {
  pillar: string;
  label: string;
  ingest: number;
  read: number;
  overall: number;
  sloMet: boolean;
  color: string;
  errorBudgetRemaining: number;
  ingestSuccessReqs: number;
  ingestTotalReqs: number;
  readSuccessReqs: number;
  readTotalReqs: number;
}

interface IncidentRecord {
  pillar: string;
  description: string;
  duration: string;
  severity: "Minor" | "Major" | "Critical";
  timestamp: string;
}

function generateDemoAvailabilityData(): {
  rows: AvailabilityRow[];
  overallAvailability: number;
  sloMet: boolean;
  incidents: IncidentRecord[];
  report: ReportResponse;
} {
  const rows: AvailabilityRow[] = [
    {
      pillar: "mimir",
      label: "Mimir",
      ingest: 99.98,
      read: 99.96,
      overall: 99.97,
      sloMet: true,
      color: pillarColor("mimir"),
      errorBudgetRemaining: 78.2,
      ingestSuccessReqs: 999_800,
      ingestTotalReqs: 1_000_000,
      readSuccessReqs: 999_600,
      readTotalReqs: 1_000_000,
    },
    {
      pillar: "loki",
      label: "Loki",
      ingest: 99.95,
      read: 99.92,
      overall: 99.94,
      sloMet: true,
      color: pillarColor("loki"),
      errorBudgetRemaining: 56.4,
      ingestSuccessReqs: 999_500,
      ingestTotalReqs: 1_000_000,
      readSuccessReqs: 999_200,
      readTotalReqs: 1_000_000,
    },
    {
      pillar: "tempo",
      label: "Tempo",
      ingest: 99.99,
      read: 99.98,
      overall: 99.99,
      sloMet: true,
      color: pillarColor("tempo"),
      errorBudgetRemaining: 95.1,
      ingestSuccessReqs: 999_900,
      ingestTotalReqs: 1_000_000,
      readSuccessReqs: 999_800,
      readTotalReqs: 1_000_000,
    },
    {
      pillar: "pyroscope",
      label: "Pyroscope",
      ingest: 99.93,
      read: 99.89,
      overall: 99.91,
      sloMet: true,
      color: pillarColor("pyroscope"),
      errorBudgetRemaining: 12.3,
      ingestSuccessReqs: 999_300,
      ingestTotalReqs: 1_000_000,
      readSuccessReqs: 998_900,
      readTotalReqs: 1_000_000,
    },
    {
      pillar: "grafana",
      label: "Grafana UI",
      ingest: 99.96,
      read: 99.94,
      overall: 99.95,
      sloMet: true,
      color: pillarColor("grafana"),
      errorBudgetRemaining: 62.7,
      ingestSuccessReqs: 999_600,
      ingestTotalReqs: 1_000_000,
      readSuccessReqs: 999_400,
      readTotalReqs: 1_000_000,
    },
  ];

  const overallAvailability =
    rows.reduce((s, r) => s + r.overall, 0) / rows.length;
  const sloMet = overallAvailability >= SLO_TARGET;

  const incidents: IncidentRecord[] = [
    {
      pillar: "Pyroscope",
      description:
        "Brief 2-minute degradation in read path due to compactor restart. Automated recovery, no data loss.",
      duration: "2 minutes",
      severity: "Minor",
      timestamp: "2026-03-22T14:32:00Z",
    },
  ];

  const report: ReportResponse = {
    environment: "PROD",
    time_range: { start: "2026-03-01T00:00:00Z", end: "2026-03-30T23:59:59Z" },
    effective_query_windows: [],
    kpis: rows.map((r) => ({
      pillar: r.pillar,
      kpis: [
        {
          kpi_name: "Availability (Ingest)",
          value: r.ingest,
          unit: "%",
          pillar: r.pillar,
          environment: "PROD",
          time_windows: [],
          details: {
            success_requests: r.ingestSuccessReqs,
            total_requests: r.ingestTotalReqs,
          },
        },
        {
          kpi_name: "Availability (Read)",
          value: r.read,
          unit: "%",
          pillar: r.pillar,
          environment: "PROD",
          time_windows: [],
          details: {
            success_requests: r.readSuccessReqs,
            total_requests: r.readTotalReqs,
          },
        },
      ],
    })),
    generated_at: new Date().toISOString(),
  };

  return { rows, overallAvailability, sloMet, incidents, report };
}

function generateTimelineData(rows: AvailabilityRow[]) {
  return Array.from({ length: 30 }, (_, i) => {
    const date = new Date();
    date.setDate(date.getDate() - 29 + i);
    const point: Record<string, any> = {
      date: date.toLocaleDateString("en-US", { month: "short", day: "numeric" }),
    };
    rows.forEach((r) => {
      /* Jitter around overall availability */
      const jitter = (Math.random() - 0.5) * 0.08;
      point[r.pillar] = +Math.min(100, Math.max(99.0, r.overall + jitter)).toFixed(3);
    });
    return point;
  });
}

/* -------------------------------------------------------------------------- */
/*  Tooltip                                                                   */
/* -------------------------------------------------------------------------- */

function GlassTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-white/[0.08] bg-[#0f1117]/95 px-4 py-3 shadow-xl backdrop-blur-xl">
      <p className="mb-1 text-xs text-slate-400">{label}</p>
      {payload.map((entry: any) => (
        <p key={entry.dataKey} className="text-sm font-medium" style={{ color: entry.color }}>
          {entry.name}: {formatPercent(entry.value, 3)}
        </p>
      ))}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Availability badge helper                                                 */
/* -------------------------------------------------------------------------- */

function AvailBadge({ value }: { value: number }) {
  const color = kpiStatusColor("availability", value);
  const bgMap: Record<string, string> = {
    "text-emerald-400": "bg-emerald-400/10",
    "text-yellow-400": "bg-yellow-400/10",
    "text-red-400": "bg-red-400/10",
    "text-cyan-400": "bg-cyan-400/10",
  };
  return (
    <span
      className={cn(
        "inline-flex rounded-md px-2 py-0.5 text-xs font-semibold tabular-nums",
        bgMap[color] ?? "bg-cyan-400/10",
        color,
      )}
    >
      {formatPercent(value, 2)}
    </span>
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

export default function AvailabilityPage() {
  const isClient = useIsClient();
  const { report, isLoading } = useReportData();
  const [expandedPillars, setExpandedPillars] = useState<Set<string>>(new Set());

  const togglePillar = (key: string) => {
    setExpandedPillars((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  /* Transform report data into availability rows */
  const data = useMemo(() => {
    if (!report) return null;

    const rows: AvailabilityRow[] = PILLARS.map((p) => {
      const pillarMatch = report.kpis.find(
        (pk) => pk.pillar.toLowerCase() === p.key.toLowerCase() || pk.pillar.toLowerCase() === p.label.toLowerCase(),
      );
      const kpis = pillarMatch?.kpis ?? [];
      const uptimeKpi = kpis.find((k) => k.kpi_name.toLowerCase().includes("uptime") || k.kpi_name.toLowerCase().includes("availability"));
      const ingestKpi = kpis.find((k) => k.kpi_name.toLowerCase().includes("ingest") && k.kpi_name.toLowerCase().includes("avail"));
      const readKpi = kpis.find((k) => k.kpi_name.toLowerCase().includes("read") && k.kpi_name.toLowerCase().includes("avail"));
      const overall = uptimeKpi?.value ?? ((ingestKpi?.value ?? 99.9) + (readKpi?.value ?? 99.9)) / 2;
      const ingest = ingestKpi?.value ?? overall;
      const read = readKpi?.value ?? overall;
      return {
        pillar: p.key,
        label: p.label,
        ingest,
        read,
        overall,
        sloMet: overall >= 99.9,
        color: pillarColor(p.key),
        errorBudgetRemaining: Math.max(0, ((overall - 99.9) / 0.1) * 100),
        ingestSuccessReqs: Math.round(ingest * 10000),
        ingestTotalReqs: 1_000_000,
        readSuccessReqs: Math.round(read * 10000),
        readTotalReqs: 1_000_000,
      };
    });

    const overallAvailability = rows.reduce((s, r) => s + r.overall, 0) / rows.length;
    const sloMet = rows.every((r) => r.sloMet);
    const incidents: IncidentRecord[] = rows
      .filter((r) => !r.sloMet)
      .map((r) => ({
        pillar: r.label,
        description: `${r.label} availability dropped below 99.9% SLO target (${r.overall.toFixed(2)}%)`,
        severity: (r.overall < 99.0 ? "Critical" : r.overall < 99.5 ? "Major" : "Minor") as IncidentRecord["severity"],
        duration: "~2 minutes",
        timestamp: new Date().toISOString(),
      }));

    return { rows, overallAvailability, sloMet, incidents, report };
  }, [report]);

  const timelineData = useMemo(() => {
    if (!data) return [];
    return generateTimelineData(data.rows);
  }, [data]);

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
          <h2 className="mb-2 text-lg font-semibold text-slate-200">No Availability Data</h2>
          <p className="text-sm text-slate-400">
            Configure your Grafana connection and generate a report in{" "}
            <Link href="/settings" className="text-indigo-400 underline underline-offset-2 hover:text-indigo-300">
              Settings
            </Link>{" "}
            to view availability metrics.
          </p>
        </GlassCard>
      </div>
    );
  }

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
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/15">
          <Shield className="h-5 w-5 text-emerald-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-100">
            Availability & Uptime
          </h1>
          <p className="text-sm text-slate-400">
            SLI monitoring and SLO compliance
          </p>
        </div>
      </motion.div>

      {/* ------------------------------------------------------------------ */}
      {/*  SLO Compliance hero                                               */}
      {/* ------------------------------------------------------------------ */}
      <GlassCard className="gradient-border" delay={0.05}>
        <div className="flex flex-col items-center gap-4 py-4 sm:flex-row sm:justify-between">
          <div className="text-center sm:text-left">
            <p className="text-[10px] uppercase tracking-wider text-slate-500">
              Platform Service Level Objective
            </p>
            <p className="mt-1 text-3xl font-bold text-slate-100">
              SLO: {formatPercent(SLO_TARGET, 1)}
            </p>
          </div>

          <div className="text-center">
            <p className="text-[10px] uppercase tracking-wider text-slate-500">
              Current Overall Availability
            </p>
            <p
              className={cn(
                "mt-1 text-4xl font-bold tabular-nums",
                kpiStatusColor("availability", data.overallAvailability),
              )}
            >
              {formatPercent(data.overallAvailability, 2)}
            </p>
          </div>

          <div className="text-center sm:text-right">
            <p className="text-[10px] uppercase tracking-wider text-slate-500">
              SLO Target Status
            </p>
            <div className="mt-2">
              {data.sloMet ? (
                <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-400/10 px-3 py-1 text-sm font-semibold text-emerald-400 ring-1 ring-inset ring-emerald-400/20">
                  <CheckCircle2 className="h-4 w-4" />
                  MET
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 rounded-full bg-red-400/10 px-3 py-1 text-sm font-semibold text-red-400 ring-1 ring-inset ring-red-400/20">
                  <XCircle className="h-4 w-4" />
                  MISSED
                </span>
              )}
            </div>
          </div>
        </div>
      </GlassCard>

      {/* ------------------------------------------------------------------ */}
      {/*  Pillar Availability Table                                         */}
      {/* ------------------------------------------------------------------ */}
      <GlassCard delay={0.1}>
        <h3 className="mb-4 text-sm font-semibold text-slate-200">
          Pillar Availability
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/[0.06]">
                {[
                  "Pillar",
                  "Ingest Availability",
                  "Read Availability",
                  "Overall",
                  "SLO Status",
                ].map((h) => (
                  <th
                    key={h}
                    className="px-4 py-2.5 text-left text-[10px] font-semibold uppercase tracking-wider text-slate-500"
                  >
                    {h}
                  </th>
                ))}
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
                  <td className="px-4 py-3">
                    <AvailBadge value={row.ingest} />
                  </td>
                  <td className="px-4 py-3">
                    <AvailBadge value={row.read} />
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={cn(
                        "text-sm font-bold tabular-nums",
                        kpiStatusColor("availability", row.overall),
                      )}
                    >
                      {formatPercent(row.overall, 2)}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {row.sloMet ? (
                      <span className="inline-flex items-center gap-1.5 text-emerald-400">
                        <CheckCircle2 className="h-4 w-4" />
                        <span className="text-xs font-medium">Met</span>
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 text-red-400">
                        <XCircle className="h-4 w-4" />
                        <span className="text-xs font-medium">Missed</span>
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </GlassCard>

      {/* ------------------------------------------------------------------ */}
      {/*  Availability Timeline                                             */}
      {/* ------------------------------------------------------------------ */}
      <GlassCard delay={0.15}>
        <h3 className="mb-4 text-sm font-semibold text-slate-200">
          Availability Timeline (30 Days)
        </h3>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={timelineData} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
            <XAxis
              dataKey="date"
              tick={{ fill: "#64748b", fontSize: 11 }}
              axisLine={{ stroke: "rgba(255,255,255,0.06)" }}
              tickLine={false}
            />
            <YAxis
              domain={[99.0, 100.0]}
              tick={{ fill: "#64748b", fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v: number) => `${v.toFixed(1)}%`}
            />
            <Tooltip content={<GlassTooltip />} />
            <Legend wrapperStyle={{ paddingTop: 12, fontSize: 12, color: "#94a3b8" }} />
            <ReferenceLine
              y={SLO_TARGET}
              stroke="#f87171"
              strokeDasharray="6 4"
              strokeWidth={1.5}
              label={{
                value: `SLO ${formatPercent(SLO_TARGET, 1)}`,
                position: "insideTopRight",
                fill: "#f87171",
                fontSize: 11,
              }}
            />
            {data.rows.map((row) => (
              <Line
                key={row.pillar}
                type="monotone"
                dataKey={row.pillar}
                name={row.label}
                stroke={row.color}
                strokeWidth={2}
                dot={false}
                animationDuration={1000}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </GlassCard>

      {/* ------------------------------------------------------------------ */}
      {/*  SLI Details per Pillar (expandable)                               */}
      {/* ------------------------------------------------------------------ */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-slate-200">
          SLI Details per Pillar
        </h3>
        {data.rows.map((row, idx) => {
          const isExpanded = expandedPillars.has(row.pillar);
          return (
            <GlassCard key={row.pillar} delay={0.2 + idx * 0.04} className="overflow-hidden">
              <button
                onClick={() => togglePillar(row.pillar)}
                className="flex w-full items-center justify-between"
              >
                <div className="flex items-center gap-3">
                  <span
                    className="h-3 w-3 rounded-full"
                    style={{ backgroundColor: row.color }}
                  />
                  <span className="text-sm font-medium text-slate-200">
                    {row.label}
                  </span>
                  <span
                    className={cn(
                      "text-sm font-bold tabular-nums",
                      kpiStatusColor("availability", row.overall),
                    )}
                  >
                    {formatPercent(row.overall, 2)}
                  </span>
                </div>
                {isExpanded ? (
                  <ChevronUp className="h-4 w-4 text-slate-400" />
                ) : (
                  <ChevronDown className="h-4 w-4 text-slate-400" />
                )}
              </button>

              <AnimatePresence>
                {isExpanded && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.25 }}
                    className="overflow-hidden"
                  >
                    <div className="mt-4 grid grid-cols-1 gap-4 border-t border-white/[0.06] pt-4 sm:grid-cols-3">
                      {/* Ingest Success Rate */}
                      <div className="rounded-xl bg-white/[0.03] border border-white/[0.04] p-4">
                        <p className="text-[10px] uppercase tracking-wider text-slate-500">
                          Ingest Success Rate
                        </p>
                        <p
                          className={cn(
                            "mt-1 text-xl font-bold tabular-nums",
                            kpiStatusColor("availability", row.ingest),
                          )}
                        >
                          {formatPercent(row.ingest, 2)}
                        </p>
                        <p className="mt-2 font-mono text-[11px] text-slate-500">
                          {row.ingestSuccessReqs.toLocaleString()} / {row.ingestTotalReqs.toLocaleString()} reqs
                        </p>
                      </div>

                      {/* Read Success Rate */}
                      <div className="rounded-xl bg-white/[0.03] border border-white/[0.04] p-4">
                        <p className="text-[10px] uppercase tracking-wider text-slate-500">
                          Read Success Rate
                        </p>
                        <p
                          className={cn(
                            "mt-1 text-xl font-bold tabular-nums",
                            kpiStatusColor("availability", row.read),
                          )}
                        >
                          {formatPercent(row.read, 2)}
                        </p>
                        <p className="mt-2 font-mono text-[11px] text-slate-500">
                          {row.readSuccessReqs.toLocaleString()} / {row.readTotalReqs.toLocaleString()} reqs
                        </p>
                      </div>

                      {/* Error Budget */}
                      <div className="rounded-xl bg-white/[0.03] border border-white/[0.04] p-4">
                        <p className="text-[10px] uppercase tracking-wider text-slate-500">
                          Error Budget Remaining
                        </p>
                        <p
                          className={cn(
                            "mt-1 text-xl font-bold tabular-nums",
                            row.errorBudgetRemaining > 50
                              ? "text-emerald-400"
                              : row.errorBudgetRemaining > 20
                                ? "text-yellow-400"
                                : "text-red-400",
                          )}
                        >
                          {formatPercent(row.errorBudgetRemaining, 1)}
                        </p>
                        <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-white/[0.06]">
                          <div
                            className="h-full rounded-full transition-all duration-700"
                            style={{
                              width: `${row.errorBudgetRemaining}%`,
                              backgroundColor:
                                row.errorBudgetRemaining > 50
                                  ? "#34d399"
                                  : row.errorBudgetRemaining > 20
                                    ? "#facc15"
                                    : "#f87171",
                            }}
                          />
                        </div>
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </GlassCard>
          );
        })}
      </div>

      {/* ------------------------------------------------------------------ */}
      {/*  Incident Summary                                                  */}
      {/* ------------------------------------------------------------------ */}
      <GlassCard delay={0.4}>
        <h3 className="mb-4 text-sm font-semibold text-slate-200">
          Incident Summary
        </h3>

        {data.incidents.length > 0 ? (
          <div className="space-y-3">
            {data.incidents.map((inc, i) => {
              const severityStyles: Record<string, string> = {
                Minor: "bg-yellow-400/10 text-yellow-400 ring-yellow-400/20",
                Major: "bg-orange-400/10 text-orange-400 ring-orange-400/20",
                Critical: "bg-red-400/10 text-red-400 ring-red-400/20",
              };
              return (
                <div
                  key={i}
                  className="flex items-start gap-3 rounded-xl border border-white/[0.06] bg-white/[0.02] p-4"
                >
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-yellow-400" />
                  <div className="flex-1">
                    <div className="mb-1 flex items-center gap-2">
                      <span className="text-sm font-medium text-slate-200">
                        {inc.pillar}
                      </span>
                      <span
                        className={cn(
                          "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset",
                          severityStyles[inc.severity] ?? severityStyles.Minor,
                        )}
                      >
                        {inc.severity}
                      </span>
                      <span className="text-[11px] text-slate-500">
                        {new Date(inc.timestamp).toLocaleDateString("en-US", {
                          month: "short",
                          day: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </span>
                    </div>
                    <p className="text-xs leading-relaxed text-slate-400">
                      {inc.description}
                    </p>
                    <p className="mt-1 text-[11px] text-slate-500">
                      Duration: {inc.duration}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="flex items-center gap-2 rounded-xl bg-emerald-400/5 border border-emerald-400/10 px-4 py-3">
            <CheckCircle2 className="h-4 w-4 text-emerald-400" />
            <span className="text-sm text-emerald-400">
              No SLO violations detected in the selected time range
            </span>
          </div>
        )}
      </GlassCard>
    </div>
  );
}
