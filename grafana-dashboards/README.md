# Observability KPI -- Grafana Dashboards, Alerts & Recording Rules

Production-grade Grafana dashboards and rule sets for the full **LGTM + Pyroscope**
observability stack (Grafana, Mimir, Loki, Tempo, Pyroscope).  Designed for
platform / SRE teams operating multi-cluster, multi-stack Kubernetes
environments.

---

## Architecture

```
  +-------------------+     +-------------------+     +-------------------+
  |   Applications    |     |   Applications    |     |   Applications    |
  |   (Cluster A)     |     |   (Cluster B)     |     |   (Cluster N)     |
  +--------+----------+     +--------+----------+     +--------+----------+
           |                         |                         |
           |  metrics / logs / traces / profiles               |
           v                         v                         v
  +--------+-------------------------+-------------------------+--------+
  |                        Grafana Agent / Alloy                        |
  |  (OpenTelemetry Collector -- scrapes, tails, instruments)           |
  +-----+------------+------------+------------+------------------------+
        |            |            |            |
        v            v            v            v
  +---------+  +---------+  +---------+  +------------+
  |  Mimir  |  |  Loki   |  |  Tempo  |  | Pyroscope  |
  | metrics |  |  logs   |  | traces  |  | profiles   |
  +---------+  +---------+  +---------+  +------------+
        |            |            |            |
        +------------+------------+------------+
                     |
                     v
             +---------------+
             |   Grafana     |
             |  Dashboards   |  <--- this repository
             |  Alert Rules  |
             | Recording Rls |
             +---------------+
```

Every dashboard enforces the **cluster -> stack -> namespace** variable
hierarchy so that operators can slice data across any dimension at any time.

---

## Dashboard Catalog

| Dashboard | UID | Datasources | Signals | Description |
|---|---|---|---|---|
| **Application Overview -- Four Signal Correlation** | `app-overview-4signal` | Mimir, Loki, Tempo, Pyroscope | Metrics, Logs, Traces, Profiles | Executive entry point for service health. RED metrics, SLO burn, error logs, traces, and profiling flamegraphs on a single pane. |
| **Loki -- Logs Deep Dive & Pattern Analysis** | `loki-logs-deep-dive` | Loki, Tempo | Logs, Traces | Expert LogQL deep dive with pattern matching, unwrap metrics, quantile_over_time, structured metadata, and log-to-trace correlation. |
| **Tempo -- Distributed Tracing & Service Graph** | `tempo-tracing-deep-dive` | Tempo, Mimir, Loki | Traces, Metrics, Logs | TraceQL search, service graph, span RED metrics, duration distributions, error analysis, and cross-signal links. |
| **Pyroscope -- Continuous Profiling & Flamegraphs** | `pyroscope-profiling` | Pyroscope, Mimir | Profiles, Metrics | CPU, memory, goroutine, mutex, and block profiles correlated with resource metrics. |

---

## Template Variables

All dashboards share a common variable chain to support multi-cluster,
multi-stack environments.

| Variable | Type | Query / Values | Description |
|---|---|---|---|
| `$datasource` | datasource | `prometheus` | Prometheus/Mimir datasource selector. Never hardcoded. |
| `$cluster` | query | `label_values(up, cluster)` | Kubernetes cluster selector |
| `$stack` | query | `label_values(up{cluster=~"$cluster"}, stack)` | Stack / environment within a cluster |
| `$namespace` | query | `label_values(up{cluster=~"$cluster", stack=~"$stack"}, namespace)` | Kubernetes namespace |
| `$job` | query | `label_values(up{...}, job)` | Service / job (dashboard-specific) |

Every PromQL / LogQL / TraceQL query includes
`{cluster=~"$cluster", stack=~"$stack", namespace=~"$namespace"}` as standard
label matchers.

---

## Cross-Signal Correlation

The dashboards are wired together to enable seamless drill-down across the
four pillars of observability.

```
  Metrics (Mimir)
      |
      |  "View logs" link -> Loki deep dive
      |  filtered to same job + time range
      v
  Logs (Loki)
      |
      |  Extracted traceID from structured metadata
      |  -> "View trace" data link to Tempo
      v
  Traces (Tempo)
      |
      |  Span attributes carry service.name, namespace
      |  -> "View profile" link to Pyroscope
      |  -> "View logs" link back to Loki
      v
  Profiles (Pyroscope)
      |
      |  Profile labels match service/pod
      |  -> "View metrics" link back to Mimir
      +---> Full loop back to Metrics
```

**How it works in practice:**

1. **Metrics to Logs** -- The Application Overview dashboard includes data
   links on error-rate panels that open the Loki Deep Dive, pre-filtered to
   the same `job`, `namespace`, and time window.
2. **Logs to Traces** -- Log lines parsed with `logfmt` or `json` expose a
   `traceID` field.  A derived field / data link sends the user to Tempo with
   that trace ID.
3. **Traces to Profiles** -- Span attributes (`service.name`, `pod`) are used
   to build a link to Pyroscope filtered to the same service and time range.
4. **Traces to Logs** -- Tempo's span-to-logs feature links back to Loki using
   the `traceID` label or structured metadata.
5. **Profiles to Metrics** -- The Pyroscope dashboard includes resource-metric
   panels (CPU, memory) from Mimir, completing the loop.

---

## Alert Rules

### Mimir / Prometheus Alerts (`alerts/mimir-alert-rules.yaml`)

PromQL-based alerts deployed via the Mimir ruler or as `PrometheusRule` CRDs.

| Alert | Severity | For | What it detects |
|---|---|---|---|
| `HighErrorRate` | warning | 5m | HTTP 5xx error rate > 1% |
| `CriticalErrorRate` | critical | 2m | HTTP 5xx error rate > 5% |
| `HighP95Latency` | warning | 5m | P95 latency > 1 second |
| `HighP99Latency` | critical | 5m | P99 latency > 2 seconds |
| `SLOBudgetBurnRateCritical` | critical | 2m | Multi-window burn rate > 14.4x (fast burn, 1h+5m windows) |
| `SLOBudgetBurnRateHigh` | warning | 15m | Multi-window burn rate > 6x (slow burn, 6h+30m windows) |
| `PodCrashLooping` | warning | 5m | Container restarts > 3 in 1 hour |
| `CPUThrottling` | warning | 10m | CFS throttle ratio > 25% |
| `MemoryApproachingLimit` | warning | 5m | Memory working set > 90% of limit |
| `HighGoroutineCount` | warning | 10m | Goroutine count > 10,000 |
| `PersistentVolumeFilling` | warning | 10m | PV usage > 85% |
| `PersistentVolumeCritical` | critical | 5m | PV usage > 95% |

### Loki LogQL Alerts (`alerts/loki-alert-rules.yaml`)

Log-content-aware alerts deployed via the Loki ruler.

| Alert | Severity | For | What it detects |
|---|---|---|---|
| `HighErrorLogRate` | warning | 5m | > 100 error-level log lines in 5 min |
| `CriticalErrorLogRate` | critical | 2m | > 500 error-level log lines in 5 min |
| `OOMDetected` | critical | 0m | Any OOMKilled / Out of memory event |
| `PanicDetected` | critical | 0m | Any panic or fatal error in logs |
| `ConnectionRefused` | warning | 5m | > 10 connection-refused messages in 5 min |
| `TimeoutErrors` | warning | 5m | > 20 timeout messages in 5 min |
| `AuthenticationFailureSpike` | warning | 5m | > 50 auth failure messages in 5 min |
| `DNSResolutionFailure` | warning | 5m | > 5 DNS failures in 5 min |
| `DiskIOErrors` | critical | 0m | Any disk I/O or "no space" errors |
| `HighWarningLogRate` | info | 10m | > 500 warning-level log lines in 5 min |

---

## Recording Rules

### Mimir Recording Rules (`recording-rules/mimir-recording-rules.yaml`)

Pre-aggregated SLI metrics that dashboards and alerts reference.  These reduce
query-time cardinality and provide canonical metric names.

**Naming convention:** `<level>:<metric>:<operation>`

| Recording Rule | Group | What it pre-computes |
|---|---|---|
| `job:http_requests:rate5m` | request | Total request rate (5m window) |
| `job:http_requests:rate1m` | request | Total request rate (1m window) |
| `job:http_requests:rate30m` | request | Total request rate (30m window) |
| `job:http_requests:rate1h` | request | Total request rate (1h window) |
| `job:http_errors:rate5m` | request | 5xx error rate (5m) |
| `job:http_errors:rate1h` | request | 5xx error rate (1h) |
| `job:http_errors:rate6h` | request | 5xx error rate (6h) |
| `job:http_error_ratio:rate5m` | request | Error ratio (5m) |
| `job:http_error_ratio:rate1h` | request | Error ratio (1h) |
| `job:http_error_ratio:rate6h` | request | Error ratio (6h) |
| `job:http_request_duration_seconds:p50` | latency | P50 latency |
| `job:http_request_duration_seconds:p90` | latency | P90 latency |
| `job:http_request_duration_seconds:p95` | latency | P95 latency |
| `job:http_request_duration_seconds:p99` | latency | P99 latency |
| `job:http_request_duration_seconds:p999` | latency | P99.9 latency |
| `job:slo_availability:ratio5m` | SLO | 1 - error_ratio (5m) |
| `job:slo_availability:ratio1h` | SLO | 1 - error_ratio (1h) |
| `job:slo_burn_rate:5m` | SLO | Burn rate over 5m window |
| `job:slo_burn_rate:30m` | SLO | Burn rate over 30m window |
| `job:slo_burn_rate:1h` | SLO | Burn rate over 1h window |
| `job:slo_burn_rate:6h` | SLO | Burn rate over 6h window |
| `job:slo_budget_remaining:ratio` | SLO | Approximate remaining error budget |
| `namespace:container_cpu_usage:rate5m` | infra | Namespace-level CPU usage |
| `namespace:container_memory_working_set:bytes` | infra | Namespace-level memory working set |
| `namespace:container_cpu_throttle_ratio:rate5m` | infra | Namespace-level CPU throttle ratio |
| `namespace:kube_pod_restarts:increase1h` | infra | Namespace-level pod restarts |

---

## Setup Instructions

### Prerequisites

- Grafana >= 10.x (with unified alerting enabled)
- Mimir (or Prometheus-compatible TSDB) for metrics
- Loki >= 3.x for logs (with ruler enabled for LogQL alerts)
- Tempo >= 2.x for traces
- Pyroscope >= 1.x for continuous profiling
- Kubernetes cluster(s) with kube-state-metrics and cAdvisor

### Datasource Configuration

#### Mimir (Prometheus)

```yaml
apiVersion: 1
datasources:
  - name: Mimir
    type: prometheus
    access: proxy
    url: http://mimir-query-frontend.mimir.svc:8080/prometheus
    isDefault: true
    jsonData:
      httpMethod: POST
      manageAlerts: true
      prometheusType: Mimir
      exemplarTraceIdDestinations:
        - name: traceID
          datasourceUid: tempo
```

#### Loki

```yaml
  - name: Loki
    type: loki
    access: proxy
    url: http://loki-gateway.loki.svc:3100
    jsonData:
      derivedFields:
        - datasourceUid: tempo
          matcherRegex: "\"traceID\":\"(\\w+)\""
          name: TraceID
          url: "$${__value.raw}"
          urlDisplayLabel: "View Trace"
      maxLines: 5000
```

#### Tempo

```yaml
  - name: Tempo
    type: tempo
    access: proxy
    url: http://tempo-query-frontend.tempo.svc:3200
    jsonData:
      tracesToLogsV2:
        datasourceUid: loki
        filterByTraceID: true
        filterBySpanID: false
      tracesToMetrics:
        datasourceUid: mimir
      nodeGraph:
        enabled: true
      serviceMap:
        datasourceUid: mimir
```

#### Pyroscope

```yaml
  - name: Pyroscope
    type: grafana-pyroscope-datasource
    access: proxy
    url: http://pyroscope.pyroscope.svc:4040
```

---

## Deployment

### Option 1: Kubernetes with Provisioning (Recommended)

1. Deploy the provisioning config and dashboards as a ConfigMap or mount from
   a PersistentVolume:

```bash
# Copy provisioning config
kubectl create configmap grafana-provisioning-dashboards \
  --from-file=provisioning/dashboards/default.yaml \
  -n grafana

# Copy dashboard JSON files
kubectl create configmap grafana-dashboards \
  --from-file=dashboards/ \
  -n grafana
```

2. Deploy alert and recording rules to Mimir:

```bash
# Upload Mimir rules via mimirtool
mimirtool rules load \
  --address=http://mimir-ruler.mimir.svc:8080 \
  --id=<tenant-id> \
  alerts/mimir-alert-rules.yaml \
  recording-rules/mimir-recording-rules.yaml
```

3. Deploy Loki alert rules:

```bash
# Upload Loki rules via logcli or direct API
logcli rules load \
  --address=http://loki-gateway.loki.svc:3100 \
  alerts/loki-alert-rules.yaml
```

### Option 2: Docker Compose

Mount the directories directly into Grafana:

```yaml
services:
  grafana:
    image: grafana/grafana:latest
    volumes:
      - ./provisioning:/etc/grafana/provisioning
      - ./dashboards:/var/lib/grafana/dashboards
    environment:
      - GF_UNIFIED_ALERTING_ENABLED=true
```

### Option 3: Manual Import

1. Open Grafana UI
2. Navigate to **Dashboards -> Import**
3. Paste or upload each JSON file from `dashboards/`
4. Select the appropriate datasource when prompted

For alert/recording rules, use the Grafana UI under
**Alerting -> Alert Rules -> Import** or apply via the ruler HTTP API.

---

## File Structure

```
grafana-dashboards/
|-- README.md                                  # This file
|-- provisioning/
|   +-- dashboards/
|       +-- default.yaml                       # Grafana provisioning config
|-- dashboards/
|   |-- app-overview.json                      # Four-signal correlation overview
|   |-- loki-logs-deep-dive.json               # LogQL deep dive
|   |-- tempo-tracing.json                     # Distributed tracing & service graph
|   +-- pyroscope-profiling.json               # Continuous profiling & flamegraphs
|-- alerts/
|   |-- mimir-alert-rules.yaml                 # PromQL alerts (12 rules)
|   +-- loki-alert-rules.yaml                  # LogQL alerts (10 rules)
+-- recording-rules/
    +-- mimir-recording-rules.yaml             # Pre-aggregated SLIs (26 rules)
```

---

## Customisation

### Adjusting SLO Targets

The default SLO is **99.9%** (error budget = 0.001).  To change it:

1. In `recording-rules/mimir-recording-rules.yaml`, update every occurrence
   of `/ 0.001` to `/ <your_error_budget>`.  For a 99.95% SLO use `/ 0.0005`.
2. In `alerts/mimir-alert-rules.yaml`, update the burn-rate thresholds
   accordingly.  The Google SRE multi-window burn-rate table:

| Window pair | Burn-rate multiplier | Budget consumed | Detection time |
|---|---|---|---|
| 1h / 5m | 14.4x | 2% | ~1 hour |
| 6h / 30m | 6x | 5% | ~3.3 hours |
| 3d / 6h | 1x | 10% | ~3 days |

### Adding New Services

All rules use `by (cluster, namespace, job)` aggregation.  New services are
automatically picked up as long as they expose standard metrics:

- `http_requests_total` (counter with `status` label)
- `http_request_duration_seconds_bucket` (histogram)
- Standard Kubernetes metrics from kube-state-metrics and cAdvisor

### Threshold Tuning

Alert thresholds are intentionally conservative.  Tune them based on your
baseline:

```yaml
# Example: tighten error-rate warning to 0.5%
expr: ... > 0.5   # was > 1
```

---

## Contributing

1. Dashboard changes: edit the JSON, bump the `version` field, test via
   Grafana preview.
2. Alert/recording rule changes: validate YAML syntax, then test with
   `promtool check rules <file>` or `mimirtool rules check <file>`.
3. Follow the naming conventions documented above.

---

## License

Internal use.  Part of the AIOps Intelligence Hub platform.
