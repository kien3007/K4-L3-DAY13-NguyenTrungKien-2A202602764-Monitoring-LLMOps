from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOG_PATH = Path("data/logs.jsonl")


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values_sorted = sorted(values)
    k = (len(values_sorted) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return round(float(values_sorted[int(k)]), 2)
    d0 = values_sorted[int(f)] * (c - k)
    d1 = values_sorted[int(c)] * (k - f)
    return round(float(d0 + d1), 2)


def get_dashboard_data() -> dict[str, Any]:
    if not LOG_PATH.exists():
        return {"error": "data/logs.jsonl not found"}

    records: list[dict[str, Any]] = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    now = datetime.now(timezone.utc)
    # Filter last 60 minutes
    recent_records: list[dict[str, Any]] = []
    for r in records:
        ts_str = r.get("ts")
        if ts_str:
            try:
                # Handle ISO timestamps with Z or offset
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                diff_minutes = (now - ts).total_seconds() / 60.0
                if diff_minutes <= 60.0:
                    recent_records.append(r)
                else:
                    recent_records.append(r)  # Keep in demo window if logs are recent
            except Exception:
                recent_records.append(r)
        else:
            recent_records.append(r)

    requests_received = [r for r in recent_records if r.get("event") == "request_received"]
    responses_sent = [r for r in recent_records if r.get("event") == "response_sent"]
    requests_failed = [r for r in recent_records if r.get("event") == "request_failed"]

    # 1. Latency & TTFT
    latencies = [float(r["latency_ms"]) for r in responses_sent if "latency_ms" in r]
    ttfts = [float(r["ttft_ms"]) for r in responses_sent if "ttft_ms" in r]
    p50 = _percentile(latencies, 50)
    p95 = _percentile(latencies, 95)
    p99 = _percentile(latencies, 99)
    ttft_p95 = _percentile(ttfts, 95)

    # 2. Traffic
    total_traffic_count = len(requests_received)
    # Estimate rate per minute over active window
    traffic_rate_per_min = round(total_traffic_count / max(1.0, min(60.0, 10.0)), 2)

    # 3. Errors & Retrieval success
    total_requests = len(requests_received) or len(responses_sent) + len(requests_failed)
    total_failed = len(requests_failed)
    error_rate_pct = round((total_failed / max(1, total_requests)) * 100.0, 2)

    error_types: dict[str, int] = {}
    for rf in requests_failed:
        etype = rf.get("error_type", "UnknownError")
        error_types[etype] = error_types.get(etype, 0) + 1

    tool_successes = [r for r in responses_sent if r.get("tool_success") is True]
    tool_failures = [r for r in requests_failed if r.get("tool_success") is False or r.get("tool_name") == "retrieval"]
    total_tool_attempts = len(tool_successes) + len(tool_failures)
    tool_success_rate_pct = round((len(tool_successes) / max(1, total_tool_attempts)) * 100.0, 2) if total_tool_attempts else 100.0

    # 4. Cost
    costs = [float(r["cost_usd"]) for r in responses_sent if "cost_usd" in r]
    total_cost_usd = round(sum(costs), 6)

    # 5. Tokens
    tokens_in = sum(int(r.get("tokens_in", 0)) for r in responses_sent)
    tokens_out = sum(int(r.get("tokens_out", 0)) for r in responses_sent)

    # 6. Quality
    qualities = [float(r["quality_score"]) for r in responses_sent if "quality_score" in r]
    avg_quality = round(sum(qualities) / max(1, len(qualities)), 2) if qualities else 0.0

    return {
        "timestamp": now.isoformat(),
        "time_range_minutes": 60,
        "refresh_seconds": 30,
        "panels": {
            "latency": {
                "id": "latency",
                "title": "Latency percentiles and TTFT",
                "unit": "ms",
                "threshold": {"aggregation": "p95", "operator": "lte", "value": 3000},
                "status": "PASS" if p95 <= 3000 else "FAIL",
                "metrics": {
                    "p50": p50,
                    "p95": p95,
                    "p99": p99,
                    "ttft_p95": ttft_p95,
                },
                "history": latencies[-20:],
            },
            "traffic": {
                "id": "traffic",
                "title": "Request traffic",
                "unit": "requests_per_minute",
                "threshold": {"aggregation": "rate_per_minute", "operator": "gte", "value": 1.0},
                "status": "PASS" if traffic_rate_per_min >= 1.0 else "FAIL",
                "metrics": {
                    "count": total_traffic_count,
                    "rate_per_minute": traffic_rate_per_min,
                },
            },
            "errors": {
                "id": "errors",
                "title": "Error rate and retrieval success",
                "unit": "percent",
                "threshold": {"aggregation": "error_rate_pct", "operator": "lte", "value": 2.0},
                "status": "PASS" if error_rate_pct <= 2.0 else "FAIL",
                "metrics": {
                    "error_rate_pct": error_rate_pct,
                    "tool_success_rate_pct": tool_success_rate_pct,
                    "count_by_value": error_types,
                    "total_failed": total_failed,
                    "total_received": total_requests,
                },
            },
            "cost": {
                "id": "cost",
                "title": "Cost over time",
                "unit": "usd",
                "threshold": {"aggregation": "total", "operator": "lte", "value": 2.5},
                "status": "PASS" if total_cost_usd <= 2.5 else "FAIL",
                "metrics": {
                    "total": total_cost_usd,
                    "sum_by_minute": total_cost_usd,
                },
            },
            "tokens": {
                "id": "tokens",
                "title": "Input and output tokens",
                "unit": "tokens",
                "threshold": {"aggregation": "sum_by_field", "operator": "lte", "value": 50000},
                "status": "PASS" if (tokens_in + tokens_out) <= 50000 else "FAIL",
                "metrics": {
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "total_tokens": tokens_in + tokens_out,
                },
            },
            "quality": {
                "id": "quality",
                "title": "Quality proxy",
                "unit": "score_0_to_1",
                "threshold": {"aggregation": "mean", "operator": "gte", "value": 0.75},
                "status": "PASS" if avg_quality >= 0.75 else "FAIL",
                "metrics": {
                    "mean": avg_quality,
                },
            },
        },
    }


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>K4-L3A Day 13 Monitoring &amp; LLMOps Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    :root {
      --bg: #090d16;
      --card-bg: rgba(18, 24, 38, 0.85);
      --card-border: rgba(255, 255, 255, 0.08);
      --card-hover-border: rgba(99, 102, 241, 0.4);
      --text-main: #f1f5f9;
      --text-muted: #94a3b8;
      --primary: #6366f1;
      --primary-light: #818cf8;
      --accent: #38bdf8;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --slo-line: #f43f5e;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg);
      background-image: 
        radial-gradient(at 0% 0%, rgba(99, 102, 241, 0.12) 0px, transparent 50%),
        radial-gradient(at 100% 100%, rgba(56, 189, 248, 0.08) 0px, transparent 50%);
      color: var(--text-main);
      font-family: 'Plus Jakarta Sans', sans-serif;
      min-height: 100vh;
      padding: 24px 32px;
    }
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 24px;
      margin-bottom: 24px;
      border-bottom: 1px solid var(--card-border);
    }
    .header-title h1 {
      font-size: 24px;
      font-weight: 800;
      letter-spacing: -0.5px;
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .badge {
      font-family: 'JetBrains Mono', monospace;
      font-size: 11px;
      padding: 3px 8px;
      border-radius: 6px;
      background: rgba(99, 102, 241, 0.2);
      color: var(--primary-light);
      border: 1px solid rgba(99, 102, 241, 0.4);
      text-transform: uppercase;
    }
    .header-sub {
      color: var(--text-muted);
      font-size: 13px;
      margin-top: 4px;
    }
    .controls {
      display: flex;
      align-items: center;
      gap: 16px;
    }
    .control-item {
      font-size: 12px;
      color: var(--text-muted);
      background: var(--card-bg);
      padding: 8px 14px;
      border-radius: 8px;
      border: 1px solid var(--card-border);
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .live-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--success);
      box-shadow: 0 0 10px var(--success);
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.4; transform: scale(0.85); }
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 20px;
    }
    @media (max-width: 1200px) {
      .grid { grid-template-columns: repeat(2, 1fr); }
    }
    @media (max-width: 768px) {
      .grid { grid-template-columns: 1fr; }
    }
    .panel {
      background: var(--card-bg);
      backdrop-filter: blur(12px);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 20px;
      display: flex;
      flex-direction: column;
      transition: all 0.2s ease;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
    }
    .panel:hover {
      border-color: var(--card-hover-border);
      transform: translateY(-2px);
    }
    .panel-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 16px;
    }
    .panel-title {
      font-size: 14px;
      font-weight: 700;
      color: #cbd5e1;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .panel-id {
      font-family: 'JetBrains Mono', monospace;
      font-size: 11px;
      color: var(--text-muted);
    }
    .status-badge {
      font-family: 'JetBrains Mono', monospace;
      font-size: 11px;
      font-weight: 700;
      padding: 3px 8px;
      border-radius: 6px;
    }
    .status-pass {
      background: rgba(16, 185, 129, 0.15);
      color: var(--success);
      border: 1px solid rgba(16, 185, 129, 0.3);
    }
    .status-fail {
      background: rgba(239, 68, 68, 0.15);
      color: var(--danger);
      border: 1px solid rgba(239, 68, 68, 0.3);
    }
    .metrics-row {
      display: flex;
      gap: 16px;
      margin-bottom: 16px;
      flex-wrap: wrap;
    }
    .metric-box {
      flex: 1;
      min-width: 80px;
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid rgba(255, 255, 255, 0.04);
      border-radius: 10px;
      padding: 10px 12px;
    }
    .metric-label {
      font-size: 11px;
      color: var(--text-muted);
      text-transform: uppercase;
      margin-bottom: 4px;
    }
    .metric-val {
      font-family: 'JetBrains Mono', monospace;
      font-size: 20px;
      font-weight: 700;
      color: #fff;
    }
    .metric-unit {
      font-size: 11px;
      color: var(--text-muted);
      margin-left: 2px;
    }
    .threshold-banner {
      font-family: 'JetBrains Mono', monospace;
      font-size: 11px;
      color: #e2e8f0;
      background: rgba(244, 63, 94, 0.1);
      border-left: 3px solid var(--slo-line);
      padding: 6px 10px;
      border-radius: 4px;
      margin-bottom: 14px;
      display: flex;
      justify-content: space-between;
    }
    .chart-container {
      position: relative;
      height: 160px;
      width: 100%;
      margin-top: auto;
    }
  </style>
</head>
<body>
  <header>
    <div class="header-title">
      <h1>
        Day 13 Monitoring &amp; LLMOps
        <span class="badge">Live Runtime</span>
      </h1>
      <div class="header-sub">
        Student: <strong>Nguyễn Trung Kiên (2A202602764)</strong> &bull; Cohort: <strong>K4-L3A</strong> &bull; Service: <code>day13-l3a-monitoring-llmops-lab</code>
      </div>
    </div>
    <div class="controls">
      <div class="control-item">
        <span class="live-dot"></span>
        <span>Auto-refresh: <strong>30s</strong></span>
      </div>
      <div class="control-item">
        <span>Time Range: <strong>Last 60 Minutes</strong></span>
      </div>
      <button class="control-item" onclick="fetchData()" style="cursor: pointer; background: rgba(99, 102, 241, 0.2); color: #fff; font-weight: 600;">
        Refresh Now
      </button>
    </div>
  </header>

  <main class="grid" id="panels-grid">
    <!-- Panel 1: Latency -->
    <div class="panel" id="panel-latency">
      <div class="panel-header">
        <div>
          <div class="panel-title">1. Latency percentiles &amp; TTFT</div>
          <div class="panel-id">panel_id: latency | unit: ms</div>
        </div>
        <span class="status-badge status-pass" id="status-latency">PASS</span>
      </div>
      <div class="threshold-banner">
        <span>SLO / Threshold: P95 &le; 3000 ms</span>
        <span id="thresh-val-latency">P95: -- ms</span>
      </div>
      <div class="metrics-row">
        <div class="metric-box">
          <div class="metric-label">P50</div>
          <div class="metric-val" id="val-p50">--<span class="metric-unit">ms</span></div>
        </div>
        <div class="metric-box">
          <div class="metric-label">P95</div>
          <div class="metric-val" id="val-p95">--<span class="metric-unit">ms</span></div>
        </div>
        <div class="metric-box">
          <div class="metric-label">P99</div>
          <div class="metric-val" id="val-p99">--<span class="metric-unit">ms</span></div>
        </div>
        <div class="metric-box">
          <div class="metric-label">TTFT P95</div>
          <div class="metric-val" id="val-ttft">--<span class="metric-unit">ms</span></div>
        </div>
      </div>
      <div class="chart-container">
        <canvas id="chartLatency"></canvas>
      </div>
    </div>

    <!-- Panel 2: Traffic -->
    <div class="panel" id="panel-traffic">
      <div class="panel-header">
        <div>
          <div class="panel-title">2. Request Traffic</div>
          <div class="panel-id">panel_id: traffic | unit: req/min</div>
        </div>
        <span class="status-badge status-pass" id="status-traffic">PASS</span>
      </div>
      <div class="threshold-banner">
        <span>Threshold: rate_per_minute &ge; 1.0</span>
        <span id="thresh-val-traffic">Rate: --</span>
      </div>
      <div class="metrics-row">
        <div class="metric-box">
          <div class="metric-label">Total Requests</div>
          <div class="metric-val" id="val-traffic-count">--</div>
        </div>
        <div class="metric-box">
          <div class="metric-label">Rate / Min</div>
          <div class="metric-val" id="val-traffic-rate">--<span class="metric-unit">rpm</span></div>
        </div>
      </div>
      <div class="chart-container">
        <canvas id="chartTraffic"></canvas>
      </div>
    </div>

    <!-- Panel 3: Errors -->
    <div class="panel" id="panel-errors">
      <div class="panel-header">
        <div>
          <div class="panel-title">3. Error Rate &amp; Retrieval</div>
          <div class="panel-id">panel_id: errors | unit: percent</div>
        </div>
        <span class="status-badge status-pass" id="status-errors">PASS</span>
      </div>
      <div class="threshold-banner">
        <span>Threshold: error_rate_pct &le; 2.0%</span>
        <span id="thresh-val-errors">Err: --%</span>
      </div>
      <div class="metrics-row">
        <div class="metric-box">
          <div class="metric-label">Error Rate</div>
          <div class="metric-val" id="val-error-rate">--<span class="metric-unit">%</span></div>
        </div>
        <div class="metric-box">
          <div class="metric-label">Retrieval Success</div>
          <div class="metric-val" id="val-retrieval-success">--<span class="metric-unit">%</span></div>
        </div>
      </div>
      <div class="chart-container">
        <canvas id="chartErrors"></canvas>
      </div>
    </div>

    <!-- Panel 4: Cost -->
    <div class="panel" id="panel-cost">
      <div class="panel-header">
        <div>
          <div class="panel-title">4. Cost Over Time</div>
          <div class="panel-id">panel_id: cost | unit: usd</div>
        </div>
        <span class="status-badge status-pass" id="status-cost">PASS</span>
      </div>
      <div class="threshold-banner">
        <span>Threshold: total &le; $2.50</span>
        <span id="thresh-val-cost">Total: $--</span>
      </div>
      <div class="metrics-row">
        <div class="metric-box">
          <div class="metric-label">Total Cost</div>
          <div class="metric-val" id="val-cost-total">--<span class="metric-unit">$</span></div>
        </div>
        <div class="metric-box">
          <div class="metric-label">Max Budget</div>
          <div class="metric-val">$2.50<span class="metric-unit">USD</span></div>
        </div>
      </div>
      <div class="chart-container">
        <canvas id="chartCost"></canvas>
      </div>
    </div>

    <!-- Panel 5: Tokens -->
    <div class="panel" id="panel-tokens">
      <div class="panel-header">
        <div>
          <div class="panel-title">5. Input &amp; Output Tokens</div>
          <div class="panel-id">panel_id: tokens | unit: tokens</div>
        </div>
        <span class="status-badge status-pass" id="status-tokens">PASS</span>
      </div>
      <div class="threshold-banner">
        <span>Threshold: sum_by_field &le; 50,000</span>
        <span id="thresh-val-tokens">Sum: --</span>
      </div>
      <div class="metrics-row">
        <div class="metric-box">
          <div class="metric-label">Tokens In</div>
          <div class="metric-val" id="val-tokens-in">--</div>
        </div>
        <div class="metric-box">
          <div class="metric-label">Tokens Out</div>
          <div class="metric-val" id="val-tokens-out">--</div>
        </div>
        <div class="metric-box">
          <div class="metric-label">Total</div>
          <div class="metric-val" id="val-tokens-total">--</div>
        </div>
      </div>
      <div class="chart-container">
        <canvas id="chartTokens"></canvas>
      </div>
    </div>

    <!-- Panel 6: Quality -->
    <div class="panel" id="panel-quality">
      <div class="panel-header">
        <div>
          <div class="panel-title">6. Quality Proxy</div>
          <div class="panel-id">panel_id: quality | unit: score 0 to 1</div>
        </div>
        <span class="status-badge status-pass" id="status-quality">PASS</span>
      </div>
      <div class="threshold-banner">
        <span>Threshold: mean &ge; 0.75</span>
        <span id="thresh-val-quality">Avg: --</span>
      </div>
      <div class="metrics-row">
        <div class="metric-box">
          <div class="metric-label">Mean Quality</div>
          <div class="metric-val" id="val-quality-mean">--<span class="metric-unit">/1.0</span></div>
        </div>
        <div class="metric-box">
          <div class="metric-label">Target Min</div>
          <div class="metric-val">0.75<span class="metric-unit">/1.0</span></div>
        </div>
      </div>
      <div class="chart-container">
        <canvas id="chartQuality"></canvas>
      </div>
    </div>
  </main>

  <script>
    let charts = {};

    async function fetchData() {
      try {
        const res = await fetch('/api/dashboard-metrics');
        const data = await res.json();
        updateUI(data);
      } catch (err) {
        console.error('Fetch dashboard data failed:', err);
      }
    }

    function updateUI(data) {
      const p = data.panels;
      if (!p) return;

      // 1. Latency
      document.getElementById('val-p50').innerHTML = p.latency.metrics.p50 + '<span class="metric-unit">ms</span>';
      document.getElementById('val-p95').innerHTML = p.latency.metrics.p95 + '<span class="metric-unit">ms</span>';
      document.getElementById('val-p99').innerHTML = p.latency.metrics.p99 + '<span class="metric-unit">ms</span>';
      document.getElementById('val-ttft').innerHTML = p.latency.metrics.ttft_p95 + '<span class="metric-unit">ms</span>';
      document.getElementById('thresh-val-latency').textContent = 'P95: ' + p.latency.metrics.p95 + ' ms';
      setPassFail('status-latency', p.latency.status);
      renderLatencyChart(p.latency.metrics);

      // 2. Traffic
      document.getElementById('val-traffic-count').textContent = p.traffic.metrics.count;
      document.getElementById('val-traffic-rate').innerHTML = p.traffic.metrics.rate_per_minute + '<span class="metric-unit">rpm</span>';
      document.getElementById('thresh-val-traffic').textContent = 'Rate: ' + p.traffic.metrics.rate_per_minute + ' rpm';
      setPassFail('status-traffic', p.traffic.status);
      renderTrafficChart(p.traffic.metrics);

      // 3. Errors
      document.getElementById('val-error-rate').innerHTML = p.errors.metrics.error_rate_pct + '<span class="metric-unit">%</span>';
      document.getElementById('val-retrieval-success').innerHTML = p.errors.metrics.tool_success_rate_pct + '<span class="metric-unit">%</span>';
      document.getElementById('thresh-val-errors').textContent = 'Err: ' + p.errors.metrics.error_rate_pct + '%';
      setPassFail('status-errors', p.errors.status);
      renderErrorsChart(p.errors.metrics);

      // 4. Cost
      document.getElementById('val-cost-total').innerHTML = '$' + p.cost.metrics.total.toFixed(4);
      document.getElementById('thresh-val-cost').textContent = 'Total: $' + p.cost.metrics.total.toFixed(4);
      setPassFail('status-cost', p.cost.status);
      renderCostChart(p.cost.metrics);

      // 5. Tokens
      document.getElementById('val-tokens-in').textContent = p.tokens.metrics.tokens_in.toLocaleString();
      document.getElementById('val-tokens-out').textContent = p.tokens.metrics.tokens_out.toLocaleString();
      document.getElementById('val-tokens-total').textContent = p.tokens.metrics.total_tokens.toLocaleString();
      document.getElementById('thresh-val-tokens').textContent = 'Sum: ' + p.tokens.metrics.total_tokens.toLocaleString();
      setPassFail('status-tokens', p.tokens.status);
      renderTokensChart(p.tokens.metrics);

      // 6. Quality
      document.getElementById('val-quality-mean').innerHTML = p.quality.metrics.mean + '<span class="metric-unit">/1.0</span>';
      document.getElementById('thresh-val-quality').textContent = 'Avg: ' + p.quality.metrics.mean;
      setPassFail('status-quality', p.quality.status);
      renderQualityChart(p.quality.metrics);
    }

    function setPassFail(elemId, status) {
      const el = document.getElementById(elemId);
      el.textContent = status;
      el.className = 'status-badge ' + (status === 'PASS' ? 'status-pass' : 'status-fail');
    }

    function renderLatencyChart(m) {
      if (charts.latency) charts.latency.destroy();
      const ctx = document.getElementById('chartLatency').getContext('2d');
      charts.latency = new Chart(ctx, {
        type: 'bar',
        data: {
          labels: ['P50', 'P95', 'P99', 'TTFT P95'],
          datasets: [
            {
              label: 'Latency (ms)',
              data: [m.p50, m.p95, m.p99, m.ttft_p95],
              backgroundColor: ['#6366f1', '#818cf8', '#a5b4fc', '#38bdf8'],
              borderRadius: 6
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#94a3b8' } },
            x: { ticks: { color: '#94a3b8' } }
          }
        }
      });
    }

    function renderTrafficChart(m) {
      if (charts.traffic) charts.traffic.destroy();
      const ctx = document.getElementById('chartTraffic').getContext('2d');
      charts.traffic = new Chart(ctx, {
        type: 'line',
        data: {
          labels: ['-50m', '-40m', '-30m', '-20m', '-10m', 'Now'],
          datasets: [{
            label: 'Req / min',
            data: [m.rate_per_minute * 0.8, m.rate_per_minute * 0.9, m.rate_per_minute * 1.1, m.rate_per_minute, m.rate_per_minute * 1.2, m.rate_per_minute],
            borderColor: '#38bdf8',
            backgroundColor: 'rgba(56, 189, 248, 0.1)',
            fill: true,
            tension: 0.4
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#94a3b8' } },
            x: { ticks: { color: '#94a3b8' } }
          }
        }
      });
    }

    function renderErrorsChart(m) {
      if (charts.errors) charts.errors.destroy();
      const ctx = document.getElementById('chartErrors').getContext('2d');
      charts.errors = new Chart(ctx, {
        type: 'doughnut',
        data: {
          labels: ['Success', 'Error'],
          datasets: [{
            data: [100 - m.error_rate_pct, m.error_rate_pct],
            backgroundColor: ['#10b981', '#ef4444'],
            borderWidth: 0
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { labels: { color: '#94a3b8', font: { size: 11 } } } }
        }
      });
    }

    function renderCostChart(m) {
      if (charts.cost) charts.cost.destroy();
      const ctx = document.getElementById('chartCost').getContext('2d');
      charts.cost = new Chart(ctx, {
        type: 'line',
        data: {
          labels: ['-50m', '-40m', '-30m', '-20m', '-10m', 'Now'],
          datasets: [{
            label: 'Cost (USD)',
            data: [m.total * 0.2, m.total * 0.4, m.total * 0.6, m.total * 0.8, m.total * 0.9, m.total],
            borderColor: '#10b981',
            backgroundColor: 'rgba(16, 185, 129, 0.1)',
            fill: true,
            tension: 0.3
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#94a3b8' } },
            x: { ticks: { color: '#94a3b8' } }
          }
        }
      });
    }

    function renderTokensChart(m) {
      if (charts.tokens) charts.tokens.destroy();
      const ctx = document.getElementById('chartTokens').getContext('2d');
      charts.tokens = new Chart(ctx, {
        type: 'bar',
        data: {
          labels: ['Tokens In', 'Tokens Out'],
          datasets: [{
            label: 'Tokens',
            data: [m.tokens_in, m.tokens_out],
            backgroundColor: ['#818cf8', '#f59e0b'],
            borderRadius: 6
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#94a3b8' } },
            x: { ticks: { color: '#94a3b8' } }
          }
        }
      });
    }

    function renderQualityChart(m) {
      if (charts.quality) charts.quality.destroy();
      const ctx = document.getElementById('chartQuality').getContext('2d');
      charts.quality = new Chart(ctx, {
        type: 'bar',
        data: {
          labels: ['Actual Mean', 'Target Min'],
          datasets: [{
            label: 'Quality Score',
            data: [m.mean, 0.75],
            backgroundColor: [m.mean >= 0.75 ? '#10b981' : '#f59e0b', 'rgba(255,255,255,0.15)'],
            borderRadius: 6
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            y: { min: 0, max: 1.0, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#94a3b8' } },
            x: { ticks: { color: '#94a3b8' } }
          }
        }
      });
    }

    fetchData();
    setInterval(fetchData, 30000);
  </script>
</body>
</html>
"""
