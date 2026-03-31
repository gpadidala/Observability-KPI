"use client";

import { useEffect, useState, useCallback } from "react";
import { Bell, Database, FlaskConical, Search, Wifi } from "lucide-react";
import { cn } from "@/lib/utils";
import type { DataMode } from "@/lib/use-report-data";

const MODE_KEY = "obs-kpi-data-mode";

interface HealthStatus {
  status: string;
  version: string;
}

export function Header() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [dataMode, setDataMode] = useState<DataMode>("real");

  /* Read initial mode from localStorage */
  useEffect(() => {
    try {
      const saved = localStorage.getItem(MODE_KEY) as DataMode | null;
      if (saved === "demo" || saved === "real") setDataMode(saved);
    } catch { /* ignore */ }
  }, []);

  const fetchHealth = useCallback(async () => {
    try {
      const res = await fetch("/api/v1/health");
      if (res.ok) {
        const data: HealthStatus = await res.json();
        setHealth(data);
      } else {
        setHealth(null);
      }
    } catch {
      setHealth(null);
    }
  }, []);

  useEffect(() => {
    fetchHealth();
    const interval = setInterval(fetchHealth, 10_000);
    return () => clearInterval(interval);
  }, [fetchHealth]);

  const switchMode = (mode: DataMode) => {
    setDataMode(mode);
    try {
      localStorage.setItem(MODE_KEY, mode);
    } catch { /* ignore */ }
    // Reload so all pages pick up the new mode
    window.location.reload();
  };

  const isHealthy = health?.status === "healthy";

  return (
    <header className="sticky top-0 z-40 flex h-16 items-center justify-between border-b border-white/[0.06] bg-[#0a0b10]/60 px-6 backdrop-blur-xl">
      {/* Left: Title and badge */}
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-semibold tracking-tight text-slate-100">
          Observability KPI Reporting
        </h1>
        <span className="rounded-full bg-indigo-500/15 px-2.5 py-0.5 text-[11px] font-medium text-indigo-300 ring-1 ring-inset ring-indigo-500/25">
          Leadership-Grade
        </span>
      </div>

      {/* Right: Actions */}
      <div className="flex items-center gap-2">
        {/* Data Mode Toggle */}
        <div className="flex items-center rounded-xl border border-white/[0.06] bg-white/[0.02] p-0.5">
          <button
            onClick={() => switchMode("demo")}
            className={cn(
              "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-all duration-200",
              dataMode === "demo"
                ? "bg-amber-500/20 text-amber-300 shadow-[0_0_12px_rgba(251,191,36,0.15)]"
                : "text-slate-500 hover:text-slate-300"
            )}
          >
            <FlaskConical className="h-3.5 w-3.5" />
            Demo Data
          </button>
          <button
            onClick={() => switchMode("real")}
            className={cn(
              "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-all duration-200",
              dataMode === "real"
                ? "bg-emerald-500/20 text-emerald-300 shadow-[0_0_12px_rgba(52,211,153,0.15)]"
                : "text-slate-500 hover:text-slate-300"
            )}
          >
            <Database className="h-3.5 w-3.5" />
            Real Data
          </button>
        </div>

        {/* Search button */}
        <button className="flex items-center gap-2 rounded-xl border border-white/[0.06] bg-white/[0.03] px-3 py-1.5 text-xs text-slate-400 transition-colors hover:border-white/[0.1] hover:bg-white/[0.05] hover:text-slate-300">
          <Search className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">Search</span>
          <kbd className="ml-2 hidden rounded-md border border-white/[0.08] bg-white/[0.04] px-1.5 py-0.5 text-[10px] font-medium text-slate-500 sm:inline">
            Cmd+K
          </kbd>
        </button>

        {/* Notifications bell */}
        <button className="relative rounded-xl border border-white/[0.06] bg-white/[0.03] p-2 text-slate-400 transition-colors hover:border-white/[0.1] hover:bg-white/[0.05] hover:text-slate-300">
          <Bell className="h-4 w-4" />
          <span className="absolute -right-0.5 -top-0.5 flex h-2.5 w-2.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-400 opacity-75" />
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-red-500 ring-2 ring-[#0a0b10]" />
          </span>
        </button>

        {/* Health status */}
        <div className="ml-1 flex items-center gap-2 rounded-xl border border-white/[0.06] bg-white/[0.03] px-3 py-1.5">
          {health ? (
            <>
              <span
                className={cn(
                  "h-2 w-2 rounded-full",
                  isHealthy
                    ? "bg-emerald-500 shadow-[0_0_6px_rgba(52,211,153,0.5)]"
                    : "bg-yellow-500 shadow-[0_0_6px_rgba(250,204,21,0.5)]"
                )}
              />
              <span className="text-xs text-slate-400">v{health.version}</span>
            </>
          ) : (
            <>
              <span className="h-2 w-2 rounded-full bg-slate-600" />
              <span className="text-xs text-slate-500">Connecting...</span>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
