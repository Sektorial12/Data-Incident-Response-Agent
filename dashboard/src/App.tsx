import { Activity, AlertTriangle, CheckCircle2, Clock, Gauge } from "lucide-react";
import { usePoll } from "./hooks/usePoll";
import { api, type Stats } from "./lib/api";
import { IncidentFeed } from "./components/IncidentFeed";
import { IncidentDetail } from "./components/IncidentDetail";
import { StatsBar } from "./components/StatsBar";
import { useState } from "react";
import type { Incident } from "./lib/api";

export default function App() {
  const { data: stats, error: statsError } = usePoll<Stats>(() => api.stats(), 5000);
  const [selected, setSelected] = useState<Incident | null>(null);

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-border px-6 py-3 flex items-center gap-6">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-blue" />
          <span className="text-sm font-semibold tracking-tight">
            Incident Response
          </span>
          <span className="text-2xs text-ink-tertiary uppercase tracking-wider ml-1">
            Control Room
          </span>
        </div>
        <div className="flex-1" />
        <StatusPill
          icon={<Gauge className="w-3 h-3" />}
          label="MTTR"
          value={stats ? `${stats.avg_mttr_seconds.toFixed(1)}s` : "—"}
        />
        <StatusPill
          icon={<AlertTriangle className="w-3 h-3 text-amber" />}
          label="Active"
          value={stats?.active ?? "—"}
        />
        <StatusPill
          icon={<CheckCircle2 className="w-3 h-3 text-green" />}
          label="Resolved"
          value={stats?.resolved ?? "—"}
        />
        <StatusPill
          icon={<Clock className="w-3 h-3" />}
          label="Total"
          value={stats?.total ?? "—"}
        />
      </header>

      <StatsBar stats={stats} error={statsError} />

      <div className="flex-1 flex overflow-hidden">
        <div className="w-[420px] border-r border-border overflow-y-auto scrollbar-thin">
          <IncidentFeed onSelect={setSelected} selectedId={selected?.id} />
        </div>
        <div className="flex-1 overflow-y-auto scrollbar-thin">
          {selected ? (
            <IncidentDetail incident={selected} />
          ) : (
            <div className="flex items-center justify-center h-full text-ink-tertiary text-sm">
              Select an incident to view details
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StatusPill({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
}) {
  return (
    <div className="flex items-center gap-1.5">
      {icon}
      <span className="text-2xs text-ink-tertiary uppercase tracking-wider">
        {label}
      </span>
      <span className="text-sm tabular font-medium">{value}</span>
    </div>
  );
}
