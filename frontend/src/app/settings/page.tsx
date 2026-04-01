"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  Activity,
  BarChart3,
  CheckCircle2,
  Clock,
  Database,
  FileDown,
  FileJson,
  FileSpreadsheet,
  FileText,
  Flame,
  GitBranch,
  Globe,
  Key,
  Loader2,
  Lock,
  Settings,
  XCircle,
} from "lucide-react";

import { GlassCard } from "@/components/glass-card";
import { cn } from "@/lib/utils";
import {
  api,
  PILLARS,
  type EnvironmentConfig,
  type ConnectionValidation,
  type ReportResponse,
} from "@/lib/api";

/* -------------------------------------------------------------------------- */
/*  Section header helper                                                     */
/* -------------------------------------------------------------------------- */

function SectionHeader({
  icon: Icon,
  title,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
}) {
  return (
    <div className="mb-5 flex items-center gap-3">
      <Icon className="h-5 w-5 text-indigo-400" />
      <h2 className="text-base font-semibold text-slate-100">{title}</h2>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Styled input                                                              */
/* -------------------------------------------------------------------------- */

function FormInput({
  label,
  icon: Icon,
  type = "text",
  placeholder,
  value,
  onChange,
  id,
}: {
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  type?: string;
  placeholder?: string;
  value: string;
  onChange: (v: string) => void;
  id: string;
}) {
  return (
    <div className="space-y-1.5">
      <label
        htmlFor={id}
        className="block text-xs font-medium uppercase tracking-wider text-slate-500"
      >
        {label}
      </label>
      <div className="relative">
        <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5">
          <Icon className="h-4 w-4 text-slate-600" />
        </div>
        <input
          id={id}
          type={type}
          placeholder={placeholder}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full rounded-xl border border-white/[0.06] bg-white/[0.04] py-2.5 pl-10 pr-4 text-sm text-slate-200 placeholder-slate-600 transition-all focus:border-indigo-500/40 focus:outline-none focus:ring-1 focus:ring-indigo-500/20"
        />
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Quick select pill                                                         */
/* -------------------------------------------------------------------------- */

function QuickPill({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-full px-4 py-1.5 text-xs font-medium transition-all",
        active
          ? "bg-indigo-500/20 text-indigo-300 ring-1 ring-inset ring-indigo-500/40 shadow-[0_0_12px_rgba(99,102,241,0.15)]"
          : "bg-white/[0.04] text-slate-400 ring-1 ring-inset ring-white/[0.06] hover:bg-white/[0.06] hover:text-slate-300",
      )}
    >
      {label}
    </button>
  );
}

/* -------------------------------------------------------------------------- */
/*  Pillar icon map                                                           */
/* -------------------------------------------------------------------------- */

const pillarIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  mimir: BarChart3,
  loki: FileText,
  tempo: GitBranch,
  pyroscope: Flame,
  grafana: Activity,
};

/* -------------------------------------------------------------------------- */
/*  Date helpers                                                              */
/* -------------------------------------------------------------------------- */

function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function daysBetween(start: string, end: string): number {
  const ms = new Date(end).getTime() - new Date(start).getTime();
  return Math.max(0, Math.ceil(ms / 86_400_000));
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
/*  localStorage helpers                                                      */
/* -------------------------------------------------------------------------- */

const STORAGE_KEY_PREFIX = "obs-kpi-settings";

interface SavedEnvConfig {
  grafana_url: string;
  service_account_token: string;
  datasource_uids: Record<string, string>;
}

const DEFAULT_DS_UIDS: Record<string, string> = {
  mimir: "",
  loki: "",
  tempo: "",
  pyroscope: "",
  grafana: "",
};

function loadEnvConfig(env: "PERF" | "PROD"): SavedEnvConfig | null {
  try {
    const raw = localStorage.getItem(`${STORAGE_KEY_PREFIX}-${env}`);
    if (!raw) return null;
    return JSON.parse(raw) as SavedEnvConfig;
  } catch {
    return null;
  }
}

function saveEnvConfig(env: "PERF" | "PROD", config: SavedEnvConfig): void {
  try {
    localStorage.setItem(`${STORAGE_KEY_PREFIX}-${env}`, JSON.stringify(config));
  } catch {
    /* localStorage might be full or unavailable */
  }
}

/* -------------------------------------------------------------------------- */
/*  Page Component                                                            */
/* -------------------------------------------------------------------------- */

export default function SettingsPage() {
  const isClient = useIsClient();
  const router = useRouter();

  /* ---- Form state ---- */
  const [environment, setEnvironment] = useState<"PERF" | "PROD">("PERF");
  const [grafanaUrl, setGrafanaUrl] = useState("");
  const [token, setToken] = useState("");

  const [dsUIDs, setDsUIDs] = useState<Record<string, string>>({
    ...DEFAULT_DS_UIDS,
  });

  const [quickRange, setQuickRange] = useState<7 | 14 | 30 | null>(30);
  const [startDate, setStartDate] = useState(daysAgo(30));
  const [endDate, setEndDate] = useState(today());

  /* ---- Action state ---- */
  const [validating, setValidating] = useState(false);
  const [validationResult, setValidationResult] = useState<ConnectionValidation | null>(null);
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [report, setReport] = useState<ReportResponse | null>(null);
  const [exporting, setExporting] = useState<"pdf" | "csv" | "json" | null>(null);

  /* ---- Load saved settings on mount & env switch ---- */
  useEffect(() => {
    const saved = loadEnvConfig(environment);
    if (saved) {
      setGrafanaUrl(saved.grafana_url ?? "");
      setToken(saved.service_account_token ?? "");
      setDsUIDs({ ...DEFAULT_DS_UIDS, ...saved.datasource_uids });
    } else {
      setGrafanaUrl("");
      setToken("");
      setDsUIDs({ ...DEFAULT_DS_UIDS });
    }
    setValidationResult(null);
  }, [environment]);

  /* ---- Persist settings whenever they change ---- */
  useEffect(() => {
    if (!isClient) return;
    saveEnvConfig(environment, {
      grafana_url: grafanaUrl,
      service_account_token: token,
      datasource_uids: dsUIDs,
    });
  }, [isClient, environment, grafanaUrl, token, dsUIDs]);

  /* ---- Computed ---- */
  const rangeDays = useMemo(() => daysBetween(startDate, endDate), [startDate, endDate]);
  const chunkedWindows = rangeDays > 30 ? Math.ceil(rangeDays / 30) : 0;
  const isConnected = validationResult?.success === true;

  /* ---- Build config (filters out empty datasource UIDs) ---- */
  const buildConfig = useCallback((): EnvironmentConfig => {
    const filteredUIDs: Record<string, string> = {};
    for (const [k, v] of Object.entries(dsUIDs)) {
      if (v.trim()) filteredUIDs[k] = v.trim();
    }
    return {
      environment,
      grafana_url: grafanaUrl.trim(),
      service_account_token: token,
      datasource_uids: filteredUIDs,
      time_range_start: startDate,
      time_range_end: endDate,
    };
  }, [environment, grafanaUrl, token, dsUIDs, startDate, endDate]);

  /* ---- Quick range handler ---- */
  const applyQuickRange = useCallback((days: 7 | 14 | 30) => {
    setQuickRange(days);
    setStartDate(daysAgo(days));
    setEndDate(today());
  }, []);

  /* ---- Custom date handler (clears quick range) ---- */
  const handleStartChange = useCallback((v: string) => {
    setStartDate(v);
    setQuickRange(null);
  }, []);
  const handleEndChange = useCallback((v: string) => {
    setEndDate(v);
    setQuickRange(null);
  }, []);

  /* ---- Validate connection ---- */
  const handleValidate = useCallback(async () => {
    setValidating(true);
    setValidationResult(null);
    try {
      const result = await api.validateConnection(buildConfig());
      setValidationResult(result);
    } catch (err: any) {
      setValidationResult({
        success: false,
        message: err.message ?? "Connection failed",
      });
    } finally {
      setValidating(false);
    }
  }, [buildConfig]);

  /* ---- Generate report ---- */
  const handleGenerate = useCallback(async () => {
    setGenerating(true);
    setGenerateError(null);
    try {
      const result = await api.fetchKPIs(buildConfig());
      setReport(result);
      try {
        localStorage.setItem("obs-kpi-report", JSON.stringify(result));
      } catch {
        /* localStorage might be full or unavailable */
      }
      router.push("/");
    } catch (err: any) {
      setGenerateError(err.message ?? "Report generation failed");
    } finally {
      setGenerating(false);
    }
  }, [buildConfig, router]);

  /* ---- Export handlers ---- */
  const handleExport = useCallback(async (format: "pdf" | "csv" | "json") => {
    setExporting(format);
    try {
      if (format === "json" && report) {
        const blob = new Blob([JSON.stringify(report, null, 2)], {
          type: "application/json",
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `kpi-report-${environment}-${new Date().toISOString().slice(0, 10)}.json`;
        a.click();
        URL.revokeObjectURL(url);
      } else {
        const blob = await api.downloadReport(buildConfig(), format);
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `kpi-report-${environment}-${new Date().toISOString().slice(0, 10)}.${format}`;
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch {
      /* Silently handle export errors */
    } finally {
      setExporting(null);
    }
  }, [report, environment, buildConfig]);

  /* ---------------------------------------------------------------------- */
  /*  Render                                                                 */
  /* ---------------------------------------------------------------------- */
  if (!isClient) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      {/* ---- Page Header ---- */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="flex items-center gap-4"
      >
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-cyan-400 shadow-lg shadow-indigo-500/25">
          <Settings className="h-6 w-6 text-white" />
        </div>
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-100">
            Settings
          </h1>
          <p className="text-sm text-slate-500">
            Runtime configuration &middot; Connection management &middot; Report
            generation
          </p>
        </div>
      </motion.div>

      {/* ================================================================== */}
      {/*  1. Connection Settings                                            */}
      {/* ================================================================== */}
      <GlassCard delay={0.1}>
        <SectionHeader icon={Globe} title="Environment & Connection" />

        {/* Environment toggle */}
        <div className="mb-5 space-y-1.5">
          <label className="block text-xs font-medium uppercase tracking-wider text-slate-500">
            Environment
          </label>
          <div className="flex gap-2">
            {(["PERF", "PROD"] as const).map((env) => (
              <button
                key={env}
                type="button"
                onClick={() => setEnvironment(env)}
                className={cn(
                  "rounded-full px-5 py-2 text-xs font-semibold uppercase tracking-wider transition-all",
                  environment === env
                    ? env === "PERF"
                      ? "bg-cyan-500/20 text-cyan-300 ring-1 ring-inset ring-cyan-500/40 shadow-[0_0_12px_rgba(34,211,238,0.15)]"
                      : "bg-red-500/20 text-red-300 ring-1 ring-inset ring-red-500/40 shadow-[0_0_12px_rgba(248,113,113,0.15)]"
                    : "bg-white/[0.04] text-slate-500 ring-1 ring-inset ring-white/[0.06] hover:bg-white/[0.06] hover:text-slate-400",
                )}
              >
                {env}
              </button>
            ))}
          </div>
        </div>

        {/* Grafana URL */}
        <div className="space-y-4">
          <FormInput
            id="grafana-url"
            label="Grafana URL"
            icon={Lock}
            placeholder="https://grafana.example.com"
            value={grafanaUrl}
            onChange={setGrafanaUrl}
          />

          {/* Service Account Token */}
          <FormInput
            id="sa-token"
            label="Service Account Token"
            icon={Key}
            type="password"
            placeholder="glsa_xxxxxxxxxxxxxxxxxxxxxxxx"
            value={token}
            onChange={setToken}
          />
        </div>
      </GlassCard>

      {/* ================================================================== */}
      {/*  2. Datasource Configuration                                       */}
      {/* ================================================================== */}
      <GlassCard delay={0.2}>
        <SectionHeader icon={Database} title="Datasource UIDs" />

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {Object.entries(dsUIDs).map(([key, value]) => {
            const IconComp = pillarIcons[key] ?? Database;
            return (
              <FormInput
                key={key}
                id={`ds-${key}`}
                label={`${key.charAt(0).toUpperCase() + key.slice(1)} UID`}
                icon={IconComp}
                placeholder={`${key}-datasource-uid`}
                value={value}
                onChange={(v) =>
                  setDsUIDs((prev) => ({ ...prev, [key]: v }))
                }
              />
            );
          })}
        </div>
      </GlassCard>

      {/* ================================================================== */}
      {/*  3. Time Range                                                     */}
      {/* ================================================================== */}
      <GlassCard delay={0.3}>
        <SectionHeader icon={Clock} title="Query Time Range" />

        {/* Quick select */}
        <div className="mb-5 space-y-1.5">
          <label className="block text-xs font-medium uppercase tracking-wider text-slate-500">
            Quick Select
          </label>
          <div className="flex gap-2">
            {([7, 14, 30] as const).map((days) => (
              <QuickPill
                key={days}
                label={`Last ${days} Days`}
                active={quickRange === days}
                onClick={() => applyQuickRange(days)}
              />
            ))}
          </div>
        </div>

        {/* Custom dates */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <label
              htmlFor="start-date"
              className="block text-xs font-medium uppercase tracking-wider text-slate-500"
            >
              Start Date
            </label>
            <input
              id="start-date"
              type="date"
              value={startDate}
              onChange={(e) => handleStartChange(e.target.value)}
              className="w-full rounded-xl border border-white/[0.06] bg-white/[0.04] px-4 py-2.5 text-sm text-slate-200 transition-all focus:border-indigo-500/40 focus:outline-none focus:ring-1 focus:ring-indigo-500/20 [color-scheme:dark]"
            />
          </div>
          <div className="space-y-1.5">
            <label
              htmlFor="end-date"
              className="block text-xs font-medium uppercase tracking-wider text-slate-500"
            >
              End Date
            </label>
            <input
              id="end-date"
              type="date"
              value={endDate}
              onChange={(e) => handleEndChange(e.target.value)}
              className="w-full rounded-xl border border-white/[0.06] bg-white/[0.04] px-4 py-2.5 text-sm text-slate-200 transition-all focus:border-indigo-500/40 focus:outline-none focus:ring-1 focus:ring-indigo-500/20 [color-scheme:dark]"
            />
          </div>
        </div>

        {/* Chunk warning */}
        {chunkedWindows > 0 && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            className="mt-4 flex items-start gap-3 rounded-xl border border-amber-500/20 bg-amber-500/10 px-4 py-3"
          >
            <Clock className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
            <p className="text-xs leading-relaxed text-amber-300">
              Range exceeds 30 days. Queries will be automatically chunked into{" "}
              <span className="font-semibold">{chunkedWindows} windows</span>.
            </p>
          </motion.div>
        )}
      </GlassCard>

      {/* ================================================================== */}
      {/*  4. Actions                                                        */}
      {/* ================================================================== */}
      <GlassCard delay={0.4}>
        <div className="space-y-4">
          {/* Validate + Generate row */}
          <div className="flex flex-wrap gap-3">
            {/* Validate Connection */}
            <button
              type="button"
              onClick={handleValidate}
              disabled={validating || !grafanaUrl}
              className={cn(
                "inline-flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-medium transition-all disabled:cursor-not-allowed disabled:opacity-40",
                "bg-indigo-500/20 text-indigo-300 ring-1 ring-inset ring-indigo-500/30 hover:bg-indigo-500/30 hover:shadow-[0_0_20px_rgba(99,102,241,0.2)]",
              )}
            >
              {validating ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <CheckCircle2 className="h-4 w-4" />
              )}
              {validating ? "Validating..." : "Validate Connection"}
            </button>

            {/* Generate Report */}
            <button
              type="button"
              onClick={handleGenerate}
              disabled={generating || !isConnected}
              className={cn(
                "inline-flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-medium transition-all disabled:cursor-not-allowed disabled:opacity-40",
                "bg-cyan-500/20 text-cyan-300 ring-1 ring-inset ring-cyan-500/30 hover:bg-cyan-500/30 hover:shadow-[0_0_20px_rgba(34,211,238,0.2)]",
              )}
            >
              {generating ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <FileDown className="h-4 w-4" />
              )}
              {generating ? "Generating..." : "Generate Report"}
            </button>
          </div>

          {/* Validation result */}
          {validationResult && (
            <motion.div
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              className={cn(
                "flex items-center gap-3 rounded-xl px-4 py-3 text-sm",
                validationResult.success
                  ? "border border-emerald-500/20 bg-emerald-500/10 text-emerald-300"
                  : "border border-red-500/20 bg-red-500/10 text-red-300",
              )}
            >
              {validationResult.success ? (
                <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
              ) : (
                <XCircle className="h-4 w-4 shrink-0 text-red-400" />
              )}
              <span>{validationResult.message}</span>
              {validationResult.datasources && (
                <span className="ml-auto text-xs text-emerald-400/70">
                  {validationResult.datasources.length} datasource
                  {validationResult.datasources.length !== 1 ? "s" : ""} found
                </span>
              )}
            </motion.div>
          )}

          {/* Generate error */}
          {generateError && (
            <motion.div
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-center gap-3 rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300"
            >
              <XCircle className="h-4 w-4 shrink-0 text-red-400" />
              <span>{generateError}</span>
            </motion.div>
          )}

          {/* Divider */}
          <div className="border-t border-white/[0.06]" />

          {/* Export row */}
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => handleExport("pdf")}
              disabled={!report || exporting === "pdf"}
              className={cn(
                "inline-flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-medium transition-all disabled:cursor-not-allowed disabled:opacity-40",
                "bg-white/[0.04] text-slate-400 ring-1 ring-inset ring-white/[0.06] hover:bg-white/[0.06] hover:text-slate-300",
              )}
            >
              {exporting === "pdf" ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <FileDown className="h-3.5 w-3.5" />
              )}
              Export PDF
            </button>

            <button
              type="button"
              onClick={() => handleExport("csv")}
              disabled={!report || exporting === "csv"}
              className={cn(
                "inline-flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-medium transition-all disabled:cursor-not-allowed disabled:opacity-40",
                "bg-white/[0.04] text-slate-400 ring-1 ring-inset ring-white/[0.06] hover:bg-white/[0.06] hover:text-slate-300",
              )}
            >
              {exporting === "csv" ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <FileSpreadsheet className="h-3.5 w-3.5" />
              )}
              Export CSV
            </button>

            <button
              type="button"
              onClick={() => handleExport("json")}
              disabled={!report || exporting === "json"}
              className={cn(
                "inline-flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-medium transition-all disabled:cursor-not-allowed disabled:opacity-40",
                "bg-white/[0.04] text-slate-400 ring-1 ring-inset ring-white/[0.06] hover:bg-white/[0.06] hover:text-slate-300",
              )}
            >
              {exporting === "json" ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <FileJson className="h-3.5 w-3.5" />
              )}
              Export JSON
            </button>
          </div>
        </div>
      </GlassCard>
    </div>
  );
}
