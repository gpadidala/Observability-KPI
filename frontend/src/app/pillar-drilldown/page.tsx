"use client";

import { useState, useEffect, useMemo } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import { useReportData } from "@/lib/use-report-data";
import {
  Layers,
  BarChart3,
  FileText,
  GitBranch,
  Flame,
  Monitor,
  ChevronDown,
  ChevronUp,
  Activity,
  Settings,
} from "lucide-react";
import {
  AreaChart,
  Area,
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
  formatPercent,
  formatBytes,
  kpiStatusColor,
  pillarColor,
} from "@/lib/utils";
import { PILLARS, type PillarKPIs, type KPIResult } from "@/lib/api";

/* -------------------------------------------------------------------------- */
/*  Icon map                                                                  */
/* -------------------------------------------------------------------------- */

const PILLAR_ICONS: Record<string, React.ElementType> = {
  mimir: BarChart3,
  loki: FileText,
  tempo: GitBranch,
  pyroscope: Flame,
  grafana: Monitor,
};

/* -------------------------------------------------------------------------- */
/*  Demo data generator                                                       */
/* -------------------------------------------------------------------------- */

interface PillarDemoData {
  dlr: number;
  ingestionGB: number;
  uptime: number;
  cpuMax: number;
  cpuP95: number;
  memMax: number;
  memP95: number;
  droppedSamples: number;
  totalSamples: number;
  ingestAvail: number;
  readAvail: number;
}

const PILLAR_DEMO: Record<string, PillarDemoData> = {
  mimir: {
    dlr: 0.023,
    ingestionGB: 45.2,
    uptime: 99.97,
    cpuMax: 58,
    cpuP95: 52,
    memMax: 67,
    memP95: 62,
    droppedSamples: 1_150,
    totalSamples: 5_000_000,
    ingestAvail: 99.98,
    readAvail: 99.96,
  },
  loki: {
    dlr: 0.056,
    ingestionGB: 128.5,
    uptime: 99.94,
    cpuMax: 72,
    cpuP95: 65,
    memMax: 78,
    memP95: 71,
    droppedSamples: 7_200,
    totalSamples: 12_857_143,
    ingestAvail: 99.95,
    readAvail: 99.92,
  },
  tempo: {
    dlr: 0.012,
    ingestionGB: 23.1,
    uptime: 99.99,
    cpuMax: 35,
    cpuP95: 29,
    memMax: 42,
    memP95: 37,
    droppedSamples: 277,
    totalSamples: 2_310_000,
    ingestAvail: 99.99,
    readAvail: 99.98,
  },
  pyroscope: {
    dlr: 0.089,
    ingestionGB: 8.7,
    uptime: 99.91,
    cpuMax: 28,
    cpuP95: 23,
    memMax: 35,
    memP95: 30,
    droppedSamples: 774,
    totalSamples: 870_000,
    ingestAvail: 99.93,
    readAvail: 99.89,
  },
  grafana: {
    dlr: 0,
    ingestionGB: 0,
    uptime: 99.95,
    cpuMax: 45,
    cpuP95: 38,
    memMax: 52,
    memP95: 46,
    droppedSamples: 0,
    totalSamples: 0,
    ingestAvail: 99.96,
    readAvail: 99.94,
  },
};

function generateDemoPillarKPIs(pillarKey: string): PillarKPIs {
  const d = PILLAR_DEMO[pillarKey];
  const kpis: KPIResult[] = [
    {
      kpi_name: "Data Loss Rate",
      value: d.dlr,
      unit: "%",
      pillar: pillarKey,
      environment: "PROD",
      time_windows: [],
      details: {
        dropped_samples: d.droppedSamples,
        total_samples: d.totalSamples,
      },
    },
    {
      kpi_name: "Ingestion Volume",
      value: d.ingestionGB * 1e9,
      unit: "bytes",
      pillar: pillarKey,
      environment: "PROD",
      time_windows: [],
      details: { gb_ingested: d.ingestionGB },
    },
    {
      kpi_name: "Availability (Ingest)",
      value: d.ingestAvail,
      unit: "%",
      pillar: pillarKey,
      environment: "PROD",
      time_windows: [],
      details: { success_requests: 999_800, total_requests: 1_000_000 },
    },
    {
      kpi_name: "Availability (Read)",
      value: d.readAvail,
      unit: "%",
      pillar: pillarKey,
      environment: "PROD",
      time_windows: [],
      details: { success_requests: 999_600, total_requests: 1_000_000 },
    },
    {
      kpi_name: "Peak CPU",
      value: d.cpuMax,
      unit: "%",
      pillar: pillarKey,
      environment: "PROD",
      time_windows: [],
      details: { p95: d.cpuP95, max: d.cpuMax },
    },
    {
      kpi_name: "Peak Memory",
      value: d.memMax,
      unit: "%",
      pillar: pillarKey,
      environment: "PROD",
      time_windows: [],
      details: { p95: d.memP95, max: d.memMax },
    },
  ];

  return { pillar: pillarKey, kpis };
}

function generateTrendData(pillarKey: string) {
  const d = PILLAR_DEMO[pillarKey];
  const baseIngestion = d.ingestionGB / 30;
  const baseError = d.dlr;
  return Array.from({ length: 30 }, (_, i) => {
    const date = new Date();
    date.setDate(date.getDate() - 29 + i);
    return {
      date: date.toLocaleDateString("en-US", { month: "short", day: "numeric" }),
      ingestionRate: +(baseIngestion * (0.85 + Math.random() * 0.3)).toFixed(2),
      errorRate: +(baseError * (0.5 + Math.random() * 1.0)).toFixed(4),
    };
  });
}

/* -------------------------------------------------------------------------- */
/*  PromQL reference queries                                                  */
/* -------------------------------------------------------------------------- */

const PROMQL_QUERIES: Record<string, { label: string; query: string }[]> = {
  mimir: [
    {
      label: "Data Loss (Dropped)",
      query:
        'sum(rate(cortex_discarded_samples_total{cluster="prod"}[1h]))',
    },
    {
      label: "Data Loss (Total)",
      query:
        'sum(rate(cortex_ingester_ingested_samples_total{cluster="prod"}[1h]))',
    },
    {
      label: "Ingestion Volume",
      query:
        'sum(increase(cortex_ingester_ingested_samples_total{cluster="prod"}[24h]))',
    },
    {
      label: "Availability (Success)",
      query:
        'sum(rate(cortex_request_duration_seconds_count{status_code=~"2.."}[1h]))',
    },
    {
      label: "Availability (Total)",
      query:
        'sum(rate(cortex_request_duration_seconds_count[1h]))',
    },
  ],
  loki: [
    {
      label: "Data Loss (Dropped)",
      query:
        'sum(rate(loki_distributor_lines_dropped_total{cluster="prod"}[1h]))',
    },
    {
      label: "Data Loss (Total)",
      query:
        'sum(rate(loki_distributor_lines_received_total{cluster="prod"}[1h]))',
    },
    {
      label: "Ingestion Volume",
      query:
        'sum(increase(loki_distributor_bytes_received_total{cluster="prod"}[24h]))',
    },
    {
      label: "Availability (Success)",
      query:
        'sum(rate(loki_request_duration_seconds_count{status_code=~"2.."}[1h]))',
    },
    {
      label: "Availability (Total)",
      query: 'sum(rate(loki_request_duration_seconds_count[1h]))',
    },
  ],
  tempo: [
    {
      label: "Data Loss (Dropped)",
      query:
        'sum(rate(tempo_discarded_spans_total{cluster="prod"}[1h]))',
    },
    {
      label: "Data Loss (Total)",
      query:
        'sum(rate(tempo_distributor_spans_received_total{cluster="prod"}[1h]))',
    },
    {
      label: "Ingestion Volume",
      query:
        'sum(increase(tempo_distributor_bytes_received_total{cluster="prod"}[24h]))',
    },
    {
      label: "Availability (Success)",
      query:
        'sum(rate(tempo_request_duration_seconds_count{status_code=~"2.."}[1h]))',
    },
    {
      label: "Availability (Total)",
      query: 'sum(rate(tempo_request_duration_seconds_count[1h]))',
    },
  ],
  pyroscope: [
    {
      label: "Data Loss (Dropped)",
      query:
        'sum(rate(pyroscope_discarded_samples_total{cluster="prod"}[1h]))',
    },
    {
      label: "Data Loss (Total)",
      query:
        'sum(rate(pyroscope_ingested_samples_total{cluster="prod"}[1h]))',
    },
    {
      label: "Ingestion Volume",
      query:
        'sum(increase(pyroscope_ingested_bytes_total{cluster="prod"}[24h]))',
    },
    {
      label: "Availability (Success)",
      query:
        'sum(rate(pyroscope_request_duration_seconds_count{status_code=~"2.."}[1h]))',
    },
    {
      label: "Availability (Total)",
      query: 'sum(rate(pyroscope_request_duration_seconds_count[1h]))',
    },
  ],
  grafana: [
    {
      label: "Availability (Success)",
      query:
        'sum(rate(grafana_http_request_duration_seconds_count{status_code=~"2.."}[1h]))',
    },
    {
      label: "Availability (Total)",
      query: 'sum(rate(grafana_http_request_duration_seconds_count[1h]))',
    },
    {
      label: "Dashboard Load Time P95",
      query:
        'histogram_quantile(0.95, sum(rate(grafana_http_request_duration_seconds_bucket{handler="/api/dashboards"}[1h])) by (le))',
    },
  ],
};

/* -------------------------------------------------------------------------- */
/*  Tooltip component for Recharts                                            */
/* -------------------------------------------------------------------------- */

function GlassTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-white/[0.08] bg-[#0f1117]/95 px-4 py-3 shadow-xl backdrop-blur-xl">
      <p className="mb-1 text-xs text-slate-400">{label}</p>
      {payload.map((entry: any) => (
        <p key={entry.dataKey} className="text-sm font-medium" style={{ color: entry.color }}>
          {entry.name}: {entry.value}
        </p>
      ))}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Status badge                                                              */
/* -------------------------------------------------------------------------- */

function StatusBadge({ kpiName, value }: { kpiName: string; value: number }) {
  const color = kpiStatusColor(kpiName, value);
  const bgMap: Record<string, string> = {
    "text-emerald-400": "bg-emerald-400/10 ring-emerald-400/20",
    "text-yellow-400": "bg-yellow-400/10 ring-yellow-400/20",
    "text-red-400": "bg-red-400/10 ring-red-400/20",
    "text-cyan-400": "bg-cyan-400/10 ring-cyan-400/20",
  };
  const labelMap: Record<string, string> = {
    "text-emerald-400": "Healthy",
    "text-yellow-400": "Warning",
    "text-red-400": "Critical",
    "text-cyan-400": "Info",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-medium ring-1 ring-inset",
        bgMap[color] ?? "bg-cyan-400/10 ring-cyan-400/20",
        color,
      )}
    >
      {labelMap[color] ?? "Info"}
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

export default function PillarDrilldownPage() {
  const isClient = useIsClient();
  const { report, isLoading } = useReportData();
  const [activePillar, setActivePillar] = useState<string>("mimir");
  const [promqlOpen, setPromqlOpen] = useState(false);

  /* Build pillar data from real report OR demo fallback */
  const allPillarData = useMemo(() => {
    const out: Record<string, { kpis: PillarKPIs; trend: ReturnType<typeof generateTrendData> }> = {};
    if (report) {
      /* Use real data from the report */
      PILLARS.forEach((p) => {
        const pillarMatch = report.kpis.find(
          (pk) => pk.pillar.toLowerCase() === p.key.toLowerCase() || pk.pillar.toLowerCase() === p.label.toLowerCase(),
        );
        out[p.key] = {
          kpis: pillarMatch ?? { pillar: p.label, kpis: [] },
          trend: generateTrendData(p.key),
        };
      });
    }
    return out;
  }, [report]);

  if (isLoading || !isClient) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
      </div>
    );
  }

  if (!report) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <GlassCard className="max-w-md text-center" glow="purple">
          <Settings className="mx-auto mb-4 h-10 w-10 text-slate-500" />
          <h2 className="mb-2 text-lg font-semibold text-slate-200">No Report Data</h2>
          <p className="text-sm text-slate-400">
            Configure your Grafana connection and generate a report in{" "}
            <Link href="/settings" className="text-indigo-400 underline underline-offset-2 hover:text-indigo-300">
              Settings
            </Link>{" "}
            to view pillar details.
          </p>
        </GlassCard>
      </div>
    );
  }

  const currentPillar = PILLARS.find((p) => p.key === activePillar)!;
  const currentData = allPillarData[activePillar];
  const currentDemo = PILLAR_DEMO[activePillar];
  const color = pillarColor(activePillar);

  /* Helper to find a KPI by name */
  const findKpi = (name: string): KPIResult | undefined =>
    currentData?.kpis.kpis.find((k) => k.kpi_name.toLowerCase().includes(name.toLowerCase()));

  /* Check if data is loaded */
  const hasData = !!currentData;

  if (!hasData) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <GlassCard className="max-w-md text-center">
          <Settings className="mx-auto mb-4 h-10 w-10 text-slate-500" />
          <h2 className="mb-2 text-lg font-semibold text-slate-200">No Data Available</h2>
          <p className="text-sm text-slate-400">
            Configure your Grafana connection in{" "}
            <a href="/settings" className="text-indigo-400 underline underline-offset-2 hover:text-indigo-300">
              Settings
            </a>{" "}
            to begin monitoring.
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
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-500/15">
          <Layers className="h-5 w-5 text-indigo-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-100">
            Pillar Drilldown
          </h1>
          <p className="text-sm text-slate-400">
            Deep dive into individual observability pillars
          </p>
        </div>
      </motion.div>

      {/* ------------------------------------------------------------------ */}
      {/*  Pillar selector tabs                                              */}
      {/* ------------------------------------------------------------------ */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.1 }}
        className="flex flex-wrap gap-2"
      >
        {PILLARS.map((p) => {
          const Icon = PILLAR_ICONS[p.key];
          const isActive = activePillar === p.key;
          const pColor = pillarColor(p.key);
          return (
            <button
              key={p.key}
              onClick={() => setActivePillar(p.key)}
              className={cn(
                "glass flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition-all duration-200",
                isActive
                  ? "border-opacity-60 text-white shadow-lg"
                  : "border-white/[0.06] text-slate-400 hover:bg-white/[0.04] hover:text-slate-200",
              )}
              style={
                isActive
                  ? {
                      borderColor: pColor,
                      boxShadow: `0 0 20px ${pColor}30, 0 0 60px ${pColor}10`,
                      color: pColor,
                    }
                  : undefined
              }
            >
              {Icon && <Icon className="h-4 w-4" />}
              <span>{p.fullLabel}</span>
            </button>
          );
        })}
      </motion.div>

      {/* ------------------------------------------------------------------ */}
      {/*  Pillar hero card                                                  */}
      {/* ------------------------------------------------------------------ */}
      <AnimatePresence mode="wait">
        <motion.div
          key={activePillar}
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -16 }}
          transition={{ duration: 0.35 }}
          className="space-y-6"
        >
          <GlassCard
            className="relative overflow-hidden"
            animate={false}
          >
            {/* Subtle colored glow background */}
            <div
              className="pointer-events-none absolute -right-20 -top-20 h-60 w-60 rounded-full opacity-20 blur-3xl"
              style={{ background: color }}
            />
            <div className="relative flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <div className="mb-1 flex items-center gap-2">
                  {(() => {
                    const Icon = PILLAR_ICONS[activePillar];
                    return Icon ? <Icon className="h-6 w-6" style={{ color }} /> : null;
                  })()}
                  <h2 className="text-2xl font-bold text-slate-100">
                    {currentPillar.label}
                  </h2>
                </div>
                <p className="text-sm text-slate-400">{currentPillar.fullLabel}</p>
              </div>

              <div className="flex gap-4">
                {/* Volume stat */}
                <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] px-4 py-3 text-center">
                  <p className="text-[10px] uppercase tracking-wider text-slate-500">
                    Ingestion Volume
                  </p>
                  <p className="mt-1 text-lg font-bold text-cyan-400">
                    {currentDemo.ingestionGB > 0
                      ? `${currentDemo.ingestionGB} GB`
                      : "N/A"}
                  </p>
                </div>
                {/* Uptime stat */}
                <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] px-4 py-3 text-center">
                  <p className="text-[10px] uppercase tracking-wider text-slate-500">
                    Uptime
                  </p>
                  <p className="mt-1 text-lg font-bold text-emerald-400">
                    {formatPercent(currentDemo.uptime)}
                  </p>
                </div>
                {/* DLR stat */}
                <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] px-4 py-3 text-center">
                  <p className="text-[10px] uppercase tracking-wider text-slate-500">
                    Data Loss Rate
                  </p>
                  <p
                    className={cn(
                      "mt-1 text-lg font-bold",
                      kpiStatusColor("loss", currentDemo.dlr),
                    )}
                  >
                    {formatPercent(currentDemo.dlr, 3)}
                  </p>
                </div>
              </div>
            </div>
          </GlassCard>

          {/* ---------------------------------------------------------------- */}
          {/*  KPI cards grid                                                  */}
          {/* ---------------------------------------------------------------- */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {currentData.kpis.kpis.map((kpi, idx) => (
              <GlassCard key={kpi.kpi_name} delay={idx * 0.06}>
                <div className="flex items-start justify-between">
                  <p className="text-sm font-medium text-slate-300">
                    {kpi.kpi_name}
                  </p>
                  <StatusBadge kpiName={kpi.kpi_name} value={kpi.value} />
                </div>

                <div className="mt-3 flex items-baseline gap-1.5">
                  <span
                    className={cn(
                      "text-3xl font-bold tabular-nums",
                      kpiStatusColor(kpi.kpi_name, kpi.value),
                    )}
                  >
                    {kpi.kpi_name === "Ingestion Volume"
                      ? formatBytes(kpi.value)
                      : kpi.value.toFixed(
                          kpi.kpi_name === "Data Loss Rate" ? 3 : 2,
                        )}
                  </span>
                  {kpi.kpi_name !== "Ingestion Volume" && (
                    <span className="text-sm text-slate-500">{kpi.unit}</span>
                  )}
                </div>

                {/* Details */}
                <div className="mt-3 space-y-1 border-t border-white/[0.06] pt-3">
                  {Object.entries(kpi.details).map(([key, val]) => (
                    <div
                      key={key}
                      className="flex items-center justify-between text-xs"
                    >
                      <span className="text-slate-500">
                        {key.replace(/_/g, " ")}
                      </span>
                      <span className="font-medium text-slate-300">
                        {typeof val === "number"
                          ? val.toLocaleString()
                          : String(val)}
                      </span>
                    </div>
                  ))}
                </div>
              </GlassCard>
            ))}
          </div>

          {/* ---------------------------------------------------------------- */}
          {/*  Trend Chart                                                     */}
          {/* ---------------------------------------------------------------- */}
          <GlassCard>
            <div className="mb-4 flex items-center gap-2">
              <Activity className="h-4 w-4 text-slate-400" />
              <h3 className="text-sm font-semibold text-slate-200">
                {currentPillar.label} Trends (30 Days)
              </h3>
            </div>

            <ResponsiveContainer width="100%" height={300}>
              <AreaChart data={currentData.trend} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id="gradIngestion" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={color} stopOpacity={0.3} />
                    <stop offset="100%" stopColor={color} stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="gradError" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#f87171" stopOpacity={0.3} />
                    <stop offset="100%" stopColor="#f87171" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                <XAxis
                  dataKey="date"
                  tick={{ fill: "#64748b", fontSize: 11 }}
                  axisLine={{ stroke: "rgba(255,255,255,0.06)" }}
                  tickLine={false}
                />
                <YAxis
                  yAxisId="left"
                  tick={{ fill: "#64748b", fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  label={{
                    value: "GB",
                    angle: -90,
                    position: "insideLeft",
                    style: { fill: "#64748b", fontSize: 11 },
                  }}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  tick={{ fill: "#64748b", fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  label={{
                    value: "%",
                    angle: 90,
                    position: "insideRight",
                    style: { fill: "#64748b", fontSize: 11 },
                  }}
                />
                <Tooltip content={<GlassTooltip />} />
                <Legend
                  wrapperStyle={{ paddingTop: 12, fontSize: 12, color: "#94a3b8" }}
                />
                <Area
                  yAxisId="left"
                  type="monotone"
                  dataKey="ingestionRate"
                  name="Ingestion Rate (GB)"
                  stroke={color}
                  strokeWidth={2}
                  fill="url(#gradIngestion)"
                  dot={false}
                  animationDuration={1000}
                />
                <Area
                  yAxisId="right"
                  type="monotone"
                  dataKey="errorRate"
                  name="Error Rate (%)"
                  stroke="#f87171"
                  strokeWidth={2}
                  fill="url(#gradError)"
                  dot={false}
                  animationDuration={1000}
                />
              </AreaChart>
            </ResponsiveContainer>
          </GlassCard>

          {/* ---------------------------------------------------------------- */}
          {/*  PromQL Reference (collapsible)                                  */}
          {/* ---------------------------------------------------------------- */}
          <GlassCard>
            <button
              onClick={() => setPromqlOpen((prev) => !prev)}
              className="flex w-full items-center justify-between"
            >
              <h3 className="text-sm font-semibold text-slate-200">
                Technical Details — PromQL Queries
              </h3>
              {promqlOpen ? (
                <ChevronUp className="h-4 w-4 text-slate-400" />
              ) : (
                <ChevronDown className="h-4 w-4 text-slate-400" />
              )}
            </button>

            <AnimatePresence>
              {promqlOpen && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.25 }}
                  className="overflow-hidden"
                >
                  <div className="mt-4 space-y-3">
                    {(PROMQL_QUERIES[activePillar] ?? []).map((q) => (
                      <div
                        key={q.label}
                        className="rounded-xl bg-white/[0.03] border border-white/[0.04] p-4"
                      >
                        <p className="mb-2 text-xs font-medium text-slate-300">
                          {q.label}
                        </p>
                        <code className="block font-mono text-xs text-slate-400 break-all leading-relaxed">
                          {q.query}
                        </code>
                      </div>
                    ))}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </GlassCard>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
