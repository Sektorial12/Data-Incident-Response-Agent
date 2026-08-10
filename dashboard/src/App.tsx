import { Activity, AlertTriangle, CheckCircle2, Clock, Gauge, Monitor, Settings } from "lucide-react";
import { usePoll } from "./hooks/usePoll";
import { api, type Stats } from "./lib/api";
import { IncidentFeed } from "./components/IncidentFeed";
import { IncidentDetail } from "./components/IncidentDetail";
import { StatsBar } from "./components/StatsBar";
import { ManagePanel } from "./components/ManagePanel";
import { useState } from "react";
import type { Incident } from "./lib/api";

export default function App() {
  const { data: stats, error: statsError } = usePoll<Stats>(() => api.stats(), 5000);
  const [selected, setSelected] = useState<Incident | null>(null);
  const [view, setView] = useState<"incidents" | "manage">("incidents");

  return (
    <div className="min-h-screen flex flex-col bg-canvas">
      <header className="border-b border-border px-6 py-0 flex items-center gap-6 h-[60px] bg-white shadow-sm">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-primary" />
          <span className="text-sm font-semibold tracking-tight text-ink-primary">Incident Response</span>
          <span className="text-2xs text-ink-tertiary uppercase tracking-wider ml-1">Control Room</span>
        </div>
        <nav className="flex gap-0 ml-4">
          <button onClick={() => setView("incidents")} className={`flex items-center gap-1.5 px-4 py-0 text-sm font-medium border-b-2 transition-colors h-[60px] ${view === "incidents" ? "border-primary text-primary" : "border-transparent text-ink-tertiary hover:text-ink-secondary"}`}>
            <Monitor className="w-3.5 h-3.5" /> Incidents
          </button>
          <button onClick={() => setView("manage")} className={`flex items-center gap-1.5 px-4 py-0 text-sm font-medium border-b-2 transition-colors h-[60px] ${view === "manage" ? "border-primary text-primary" : "border-transparent text-ink-tertiary hover:text-ink-secondary"}`}>
            <Settings className="w-3.5 h-3.5" /> Manage
          </button>
        </nav>
        <div className="flex-1" />
        <StatusPill icon={<Gauge className="w-3 h-3 text-ink-tertiary" />} label="MTTR" value={stats ? `${stats.avg_mttr_seconds.toFixed(1)}s` : "—"} />
        <StatusPill icon={<AlertTriangle className="w-3 h-3 text-amber" />} label="Active" value={stats?.active ?? "—"} />
        <StatusPill icon={<CheckCircle2 className="w-3 h-3 text-green" />} label="Resolved" value={stats?.resolved ?? "—"} />
        <StatusPill icon={<Clock className="w-3 h-3 text-ink-tertiary" />} label="Total" value={stats?.total ?? "—"} />
      </header>

      {view === "incidents" && <StatsBar stats={stats} error={statsError} />}

      {view === "incidents" ? (
        <div className="flex-1 flex overflow-hidden">
          <div className="w-[420px] border-r border-border overflow-y-auto scrollbar-thin bg-white">
            <IncidentFeed onSelect={setSelected} selectedId={selected?.id} />
          </div>
          <div className="flex-1 overflow-y-auto scrollbar-thin bg-surface-alt">
            {selected ? <IncidentDetail incident={selected} /> : <div className="flex items-center justify-center h-full text-ink-tertiary text-sm">Select an incident to view details</div>}
          </div>
        </div>
      ) : (
        <div className="flex-1 flex overflow-hidden">
          <div className="w-[480px] border-r border-border overflow-y-auto scrollbar-thin bg-white">
            <ManagePanel />
          </div>
          <div className="flex-1 overflow-y-auto scrollbar-thin p-6 text-sm text-ink-tertiary bg-surface-alt">
            Use the panel on the left to manage assertions, configure alert routing, and control the agent.
          </div>
        </div>
      )}
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
      <span className="text-sm tabular font-medium text-ink-primary">{value}</span>
    </div>
  );
}
