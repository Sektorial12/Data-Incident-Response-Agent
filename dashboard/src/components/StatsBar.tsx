import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import type { Stats } from "../lib/api";

export function StatsBar({
  stats,
  error,
}: {
  stats: Stats | null;
  error: string | null;
}) {
  if (error) {
    return (
      <div className="px-6 py-2 border-b border-border bg-red-subtle text-xs text-red">
        API connection failed — {error}
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="px-6 py-2 border-b border-border text-xs text-ink-muted">
        Loading metrics...
      </div>
    );
  }

  const resolutionRate =
    stats.total > 0 ? ((stats.resolved / stats.total) * 100).toFixed(0) : "0";

  const mttrTrend = stats.avg_mttr_seconds > 0 && stats.avg_mttr_seconds < 30;

  return (
    <div className="px-6 py-2.5 border-b border-border flex items-center gap-8">
      <Metric
        label="Resolution Rate"
        value={`${resolutionRate}%`}
        sub={`${stats.resolved}/${stats.total}`}
      />
      <Divider />
      <Metric
        label="Avg MTTR"
        value={`${stats.avg_mttr_seconds.toFixed(1)}s`}
        sub="mean time to resolve"
        trend={mttrTrend ? "down" : stats.avg_mttr_seconds > 0 ? "up" : "flat"}
      />
      <Divider />
      <Metric
        label="Active"
        value={String(stats.active)}
        sub="awaiting resolution"
        alert={stats.active > 0}
      />
      <Divider />
      <Metric
        label="Throughput"
        value={String(stats.total)}
        sub="all incidents"
      />
    </div>
  );
}

function Metric({
  label,
  value,
  sub,
  trend,
  alert,
}: {
  label: string;
  value: string;
  sub: string;
  trend?: "up" | "down" | "flat";
  alert?: boolean;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex items-center gap-1.5">
        <span className="text-2xs text-ink-tertiary uppercase tracking-wider">
          {label}
        </span>
        {trend === "down" && <TrendingDown className="w-3 h-3 text-green" />}
        {trend === "up" && <TrendingUp className="w-3 h-3 text-amber" />}
        {trend === "flat" && <Minus className="w-3 h-3 text-ink-muted" />}
      </div>
      <div
        className={`text-lg tabular font-semibold ${
          alert ? "text-amber" : "text-ink-primary"
        }`}
      >
        {value}
      </div>
      <span className="text-2xs text-ink-muted">{sub}</span>
    </div>
  );
}

function Divider() {
  return <div className="w-px h-8 bg-border" />;
}
