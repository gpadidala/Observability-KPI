import type { ReportResponse, KPIResult, PillarKPIs } from "@/lib/api";
import { PILLARS } from "@/lib/api";

/**
 * Generates a complete, realistic ReportResponse for demo/preview purposes.
 * No Grafana connection required.
 */
export function generateDemoReport(): ReportResponse {
  const now = new Date();
  const thirtyDaysAgo = new Date(now.getTime() - 30 * 86_400_000);

  const mkWindow = (offsetDays: number, durationDays: number) => {
    const start = new Date(thirtyDaysAgo.getTime() + offsetDays * 86_400_000);
    const end = new Date(start.getTime() + durationDays * 86_400_000);
    return { start: start.toISOString(), end: end.toISOString() };
  };

  const pillarData: Record<string, {
    availability: number; ingestAvail: number; readAvail: number;
    loss: number; droppedSamples: number; totalSamples: number;
    cpu: number; cpuP95: number; mem: number; memP95: number;
    costGB: number; cost: number; ingestGB: number;
  }> = {
    mimir: {
      availability: 99.97, ingestAvail: 99.98, readAvail: 99.96,
      loss: 0.023, droppedSamples: 1035, totalSamples: 4_500_000,
      cpu: 58, cpuP95: 52, mem: 67, memP95: 61,
      costGB: 331.86, cost: 15_000, ingestGB: 45.2,
    },
    loki: {
      availability: 99.94, ingestAvail: 99.95, readAvail: 99.92,
      loss: 0.056, droppedSamples: 7_193, totalSamples: 12_844_643,
      cpu: 72, cpuP95: 65, mem: 78, memP95: 71,
      costGB: 62.26, cost: 8_000, ingestGB: 128.5,
    },
    tempo: {
      availability: 99.99, ingestAvail: 99.99, readAvail: 99.98,
      loss: 0.012, droppedSamples: 277, totalSamples: 2_308_333,
      cpu: 35, cpuP95: 29, mem: 42, memP95: 37,
      costGB: 216.45, cost: 5_000, ingestGB: 23.1,
    },
    pyroscope: {
      availability: 99.91, ingestAvail: 99.93, readAvail: 99.89,
      loss: 0.089, droppedSamples: 774, totalSamples: 869_663,
      cpu: 28, cpuP95: 23, mem: 35, memP95: 30,
      costGB: 229.89, cost: 2_000, ingestGB: 8.7,
    },
    grafana: {
      availability: 99.95, ingestAvail: 99.96, readAvail: 99.94,
      loss: 0.0, droppedSamples: 0, totalSamples: 0,
      cpu: 45, cpuP95: 38, mem: 52, memP95: 46,
      costGB: 0, cost: 3_000, ingestGB: 0,
    },
  };

  const pillarKPIs: PillarKPIs[] = PILLARS.map((p) => {
    const d = pillarData[p.key];
    const kpis: KPIResult[] = [
      {
        kpi_name: "Uptime / Availability",
        value: d.availability, unit: "%", pillar: p.label,
        environment: "PROD", time_windows: [mkWindow(0, 30)],
        details: { ingest_availability: d.ingestAvail, read_availability: d.readAvail },
      },
      {
        kpi_name: "Data Loss Rate",
        value: d.loss, unit: "%", pillar: p.label,
        environment: "PROD", time_windows: [mkWindow(0, 30)],
        details: { dropped_samples: d.droppedSamples, total_samples: d.totalSamples },
      },
      {
        kpi_name: "Peak CPU Utilization",
        value: d.cpu, unit: "%", pillar: p.label,
        environment: "PROD", time_windows: [mkWindow(0, 30)],
        details: { p95: d.cpuP95, max: d.cpu },
      },
      {
        kpi_name: "Peak Memory Utilization",
        value: d.mem, unit: "%", pillar: p.label,
        environment: "PROD", time_windows: [mkWindow(0, 30)],
        details: { p95: d.memP95, max: d.mem },
      },
      {
        kpi_name: "Cost per GB Ingested",
        value: d.costGB, unit: "$/GB", pillar: p.label,
        environment: "PROD", time_windows: [mkWindow(0, 30)],
        details: {},
      },
      {
        kpi_name: "Total Monthly Cost",
        value: d.cost, unit: "$", pillar: p.label,
        environment: "PROD", time_windows: [mkWindow(0, 30)],
        details: {},
      },
      {
        kpi_name: "Ingestion Volume",
        value: d.ingestGB * 1e9, unit: "bytes", pillar: p.label,
        environment: "PROD", time_windows: [mkWindow(0, 30)],
        details: { gb_ingested: d.ingestGB },
      },
      {
        kpi_name: "Availability (Ingest)",
        value: d.ingestAvail, unit: "%", pillar: p.label,
        environment: "PROD", time_windows: [mkWindow(0, 30)],
        details: {},
      },
      {
        kpi_name: "Availability (Read)",
        value: d.readAvail, unit: "%", pillar: p.label,
        environment: "PROD", time_windows: [mkWindow(0, 30)],
        details: {},
      },
    ];
    return { pillar: p.label, kpis };
  });

  return {
    environment: "PROD",
    time_range: { start: thirtyDaysAgo.toISOString(), end: now.toISOString() },
    effective_query_windows: [mkWindow(0, 15), mkWindow(15, 15)],
    kpis: pillarKPIs,
    generated_at: now.toISOString(),
  };
}
