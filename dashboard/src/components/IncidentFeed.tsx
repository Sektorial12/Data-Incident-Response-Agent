import { AlertTriangle, CheckCircle2, Clock } from "lucide-react";
import { usePoll } from "../hooks/usePoll";
import { api, type Incident } from "../lib/api";

export function IncidentFeed({
  onSelect,
  selectedId,
}: {
  onSelect: (incident: Incident) => void;
  selectedId?: string;
}) {
  const { data: incidents, loading, error } = usePoll<Incident[]>(
    () => api.incidents(undefined, 50),
    3000
  );

  if (loading && !incidents) {
    return (
      <div className="p-4 text-sm text-ink-muted">Loading incidents...</div>
    );
  }

  if (error) {
    return (
      <div className="p-4 text-sm text-red">
        Failed to load: {error}
      </div>
    );
  }

  if (!incidents || incidents.length === 0) {
    return (
      <div className="p-4 text-sm text-ink-muted">
        No incidents recorded. Waiting for assertion failures...
      </div>
    );
  }

  return (
    <div>
      <div className="px-4 py-3 border-b border-border flex items-center justify-between bg-surface-alt">
        <span className="text-2xs uppercase tracking-wider text-ink-tertiary font-medium">
          Incident Feed
        </span>
        <span className="text-2xs text-ink-muted tabular">
          {incidents.length} total
        </span>
      </div>
      {incidents.map((inc) => (
        <IncidentRow
          key={inc.id}
          incident={inc}
          onSelect={onSelect}
          selected={inc.id === selectedId}
        />
      ))}
    </div>
  );
}

function IncidentRow({
  incident,
  onSelect,
  selected,
}: {
  incident: Incident;
  onSelect: (inc: Incident) => void;
  selected: boolean;
}) {
  const isActive = incident.status === "active";
  const datasetName = extractDatasetName(incident.dataset_urn);
  const time = formatTime(incident.created_at);
  const rootCauseCount = incident.root_causes?.length ?? 0;
  const maxConfidence = incident.root_causes
    ? Math.max(...incident.root_causes.map((rc) => rc.confidence), 0)
    : 0;

  return (
    <button
      onClick={() => onSelect(incident)}
      className={`w-full text-left px-4 py-3 border-b border-border transition-colors ${
        selected ? "bg-primary-subtle" : "hover:bg-surface-hover"
      }`}
    >
      <div className="flex items-start gap-2.5">
        <div className="mt-0.5">
          {isActive ? (
            <AlertTriangle className="w-3.5 h-3.5 text-amber" />
          ) : (
            <CheckCircle2 className="w-3.5 h-3.5 text-green" />
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-ink-primary truncate">{datasetName}</span>
            <span
              className={`text-2xs px-1.5 py-0.5 rounded tabular uppercase tracking-wider border ${
                isActive
                  ? "bg-amber-subtle text-amber border-amber-border"
                  : "bg-green-subtle text-green border-green-border"
              }`}
            >
              {incident.status}
            </span>
          </div>
          <div className="flex items-center gap-2 mt-1">
            <Clock className="w-3 h-3 text-ink-muted" />
            <span className="text-2xs text-ink-tertiary tabular">{time}</span>
            {incident.elapsed_seconds != null && (
              <span className="text-2xs text-ink-muted tabular">
                {incident.elapsed_seconds.toFixed(1)}s
              </span>
            )}
          </div>
          {rootCauseCount > 0 && (
            <div className="flex items-center gap-1.5 mt-1">
              <span className="text-2xs text-ink-muted">
                {rootCauseCount} root cause{rootCauseCount > 1 ? "s" : ""}
              </span>
              <div className="flex-1 h-1 bg-border rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary rounded-full"
                  style={{ width: `${maxConfidence * 100}%` }}
                />
              </div>
              <span className="text-2xs tabular text-ink-tertiary">
                {(maxConfidence * 100).toFixed(0)}%
              </span>
            </div>
          )}
        </div>
      </div>
    </button>
  );
}

function extractDatasetName(urn: string): string {
  if (!urn) return "unknown";
  const parts = urn.replace("urn:li:dataset:", "").split(",");
  if (parts.length >= 2) {
    return parts[1].replace(/[()]/g, "").trim();
  }
  return urn;
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}
