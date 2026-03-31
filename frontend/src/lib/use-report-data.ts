"use client";

import { useCallback, useEffect, useState } from "react";
import type { ReportResponse } from "@/lib/api";
import { generateDemoReport } from "@/lib/demo-data";

const STORAGE_KEY = "obs-kpi-report";
const MODE_KEY = "obs-kpi-data-mode"; // "demo" | "real"

export type DataMode = "demo" | "real";

/**
 * Shared hook that provides KPI report data.
 * - "demo" mode: returns generated sample data (no Grafana needed)
 * - "real" mode: reads from localStorage (set by Settings page after Generate Report)
 *
 * Mode is persisted in localStorage so all pages share it.
 */
export function useReportData() {
  const [report, setReport] = useState<ReportResponse | null>(null);
  const [mode, setModeState] = useState<DataMode>("real");
  const [isLoading, setIsLoading] = useState(true);

  /* Read mode + data on mount */
  useEffect(() => {
    try {
      const savedMode = localStorage.getItem(MODE_KEY) as DataMode | null;
      const activeMode = savedMode === "demo" ? "demo" : "real";
      setModeState(activeMode);

      if (activeMode === "demo") {
        setReport(generateDemoReport());
      } else {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored) {
          const parsed = JSON.parse(stored) as ReportResponse;
          if (parsed && parsed.environment && parsed.kpis) {
            setReport(parsed);
          }
        }
      }
    } catch {
      // corrupt or unavailable localStorage
    } finally {
      setIsLoading(false);
    }
  }, []);

  /* Switch mode */
  const setMode = useCallback((newMode: DataMode) => {
    setModeState(newMode);
    try {
      localStorage.setItem(MODE_KEY, newMode);
    } catch { /* ignore */ }

    if (newMode === "demo") {
      setReport(generateDemoReport());
    } else {
      // Try to load real data
      try {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored) {
          const parsed = JSON.parse(stored) as ReportResponse;
          if (parsed && parsed.environment && parsed.kpis) {
            setReport(parsed);
            return;
          }
        }
      } catch { /* ignore */ }
      setReport(null);
    }
  }, []);

  return { report, isLoading, mode, setMode };
}

/**
 * Helper to find a KPI value from a pillar's KPI list by name substring.
 */
export function findKpiValue(
  kpis: ReportResponse["kpis"],
  pillarKey: string,
  nameFragment: string,
): number {
  const pillar = kpis.find(
    (p) => p.pillar.toLowerCase() === pillarKey.toLowerCase(),
  );
  if (!pillar) return 0;
  const match = pillar.kpis.find((k) =>
    k.kpi_name.toLowerCase().includes(nameFragment.toLowerCase()),
  );
  return match?.value ?? 0;
}

/**
 * Aggregate a KPI across all pillars.
 */
export function aggregateKpi(
  report: ReportResponse,
  nameFragment: string,
  mode: "avg" | "max" | "sum",
): number {
  const values = report.kpis
    .map((p) => {
      const match = p.kpis.find((k) =>
        k.kpi_name.toLowerCase().includes(nameFragment.toLowerCase()),
      );
      return match?.value ?? 0;
    })
    .filter((v) => v > 0);
  if (values.length === 0) return 0;
  if (mode === "avg") return values.reduce((a, b) => a + b, 0) / values.length;
  if (mode === "max") return Math.max(...values);
  return values.reduce((a, b) => a + b, 0);
}
