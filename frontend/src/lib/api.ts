/* -------------------------------------------------------------------------- */
/*  Types                                                                     */
/* -------------------------------------------------------------------------- */

export type Environment = "PERF" | "PROD";

export interface EnvironmentConfig {
  environment: Environment;
  grafana_url: string;
  service_account_token: string;
  datasource_uids: Record<string, string>;
  time_range_start: string;
  time_range_end: string;
}

export interface TimeWindow {
  start: string;
  end: string;
}

export interface KPIResult {
  kpi_name: string;
  value: number;
  unit: string;
  pillar: string;
  environment: string;
  time_windows: TimeWindow[];
  details: Record<string, any>;
}

export interface PillarKPIs {
  pillar: string;
  kpis: KPIResult[];
}

export interface ReportResponse {
  environment: string;
  time_range: { start: string; end: string };
  effective_query_windows: TimeWindow[];
  kpis: PillarKPIs[];
  generated_at: string;
}

export interface ConnectionValidation {
  success: boolean;
  message: string;
  datasources?: string[];
}

export interface HealthResponse {
  status: string;
  version: string;
}

/* -------------------------------------------------------------------------- */
/*  Pillar definitions                                                        */
/* -------------------------------------------------------------------------- */

export const PILLARS = [
  { key: "mimir", label: "Mimir", fullLabel: "Metrics (Mimir)", icon: "BarChart3", color: "#22d3ee" },
  { key: "loki", label: "Loki", fullLabel: "Logs (Loki)", icon: "FileText", color: "#a855f7" },
  { key: "tempo", label: "Tempo", fullLabel: "Traces (Tempo)", icon: "GitBranch", color: "#34d399" },
  { key: "pyroscope", label: "Pyroscope", fullLabel: "Profiles (Pyroscope)", icon: "Flame", color: "#fb923c" },
  { key: "grafana", label: "Grafana", fullLabel: "Grafana UI", icon: "Monitor", color: "#6366f1" },
] as const;

/* -------------------------------------------------------------------------- */
/*  API Client                                                                */
/* -------------------------------------------------------------------------- */

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || body.message || `Request failed: ${res.status}`);
  }
  return res.json();
}

export const api = {
  health: () => fetchApi<HealthResponse>("/api/v1/health"),

  validateConnection: (config: EnvironmentConfig) =>
    fetchApi<ConnectionValidation>("/api/v1/validate-connection", {
      method: "POST",
      body: JSON.stringify(config),
    }),

  fetchKPIs: (config: EnvironmentConfig) =>
    fetchApi<ReportResponse>("/api/v1/kpis", {
      method: "POST",
      body: JSON.stringify(config),
    }),

  fetchPillarKPIs: (config: EnvironmentConfig, pillar: string) =>
    fetchApi<PillarKPIs>(`/api/v1/kpis/${encodeURIComponent(pillar)}`, {
      method: "POST",
      body: JSON.stringify(config),
    }),

  downloadReport: async (config: EnvironmentConfig, format: "pdf" | "csv" | "json"): Promise<Blob> => {
    const res = await fetch("/api/v1/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...config, format }),
    });
    if (!res.ok) throw new Error(`Report generation failed: ${res.status}`);
    return res.blob();
  },
};
