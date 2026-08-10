import {
  Search,
  CheckCircle2,
  Bell,
  FileText,
  ChevronRight,
} from "lucide-react";
import type { Incident, AgentResults } from "../lib/api";
import { AgentTimeline } from "./AgentTimeline";
import { RootCauseList } from "./RootCauseList";

export function IncidentDetail({ incident }: { incident: Incident }) {
  const datasetName = extractDatasetName(incident.dataset_urn);
  const assertionName = incident.assertion_urn
    .replace("urn:li:assertion:", "")
    .split(",")[0]
    .replace(/[()]/g, "");

  return (
    <div className="p-6 max-w-4xl">
      <div className="flex items-center gap-2 mb-1">
        <span
          className={`text-2xs px-1.5 py-0.5 rounded tabular uppercase tracking-wider border ${
            incident.status === "active"
              ? "bg-amber-subtle text-amber border-amber-border"
              : "bg-green-subtle text-green border-green-border"
          }`}
        >
          {incident.status}
        </span>
        {incident.dedup_key && (
          <span className="text-2xs text-ink-muted">
            dedup: {incident.dedup_key.slice(0, 30)}...
          </span>
        )}
      </div>

      <h1 className="text-xl font-semibold tracking-tight text-ink-primary mb-1">{datasetName}</h1>
      <p className="text-sm text-ink-secondary font-mono mb-4">
        {incident.dataset_urn}
      </p>

      <div className="grid grid-cols-2 gap-4 mb-6">
        <Field label="Assertion" value={assertionName} mono />
        <Field label="Error" value={incident.error_message || "—"} />
        <Field
          label="Created"
          value={formatDateTime(incident.created_at)}
          mono
        />
        <Field
          label="Resolved"
          value={incident.resolved_at ? formatDateTime(incident.resolved_at) : "—"}
          mono
        />
        {incident.elapsed_seconds != null && (
          <Field
            label="Elapsed"
            value={`${incident.elapsed_seconds.toFixed(2)}s`}
            mono
          />
        )}
      </div>

      {incident.agent_results && (
        <section className="mb-6">
          <h2 className="text-2xs uppercase tracking-wider text-primary font-medium mb-3">
            Agent Pipeline
          </h2>
          <AgentTimeline results={incident.agent_results} />
        </section>
      )}

      {incident.root_causes && incident.root_causes.length > 0 && (
        <section className="mb-6">
          <h2 className="text-2xs uppercase tracking-wider text-primary font-medium mb-3">
            Root Causes ({incident.root_causes.length})
          </h2>
          <RootCauseList causes={incident.root_causes} />
        </section>
      )}

      <section>
        <h2 className="text-2xs uppercase tracking-wider text-primary font-medium mb-3">
          Raw Data
        </h2>
        <pre className="text-2xs font-mono text-ink-secondary bg-surface-alt rounded-lg p-4 overflow-x-auto scrollbar-thin border border-border">
          {JSON.stringify(incident, null, 2)}
        </pre>
      </section>
    </div>
  );
}

function Field({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <div className="text-2xs uppercase tracking-wider text-ink-tertiary mb-1">
        {label}
      </div>
      <div
        className={`text-sm ${mono ? "font-mono tabular text-ink-secondary" : "text-ink-primary"}`}
      >
        {value}
      </div>
    </div>
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

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("en-US", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}
