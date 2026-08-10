import {
  Search,
  CheckCircle2,
  Bell,
  FileText,
  AlertCircle,
  XCircle,
} from "lucide-react";
import type { AgentResults, AgentResult } from "../lib/api";

const AGENT_ORDER = [
  { key: "tracer" as const, label: "Tracer", icon: Search },
  { key: "checker" as const, label: "Checker", icon: CheckCircle2 },
  { key: "notifier" as const, label: "Notifier", icon: Bell },
  { key: "reporter" as const, label: "Reporter", icon: FileText },
];

export function AgentTimeline({ results }: { results: AgentResults }) {
  const agents = AGENT_ORDER.map(({ key, label, icon: Icon }) => {
    const result = results[key];
    const status = result?.status || "pending";
    return { key, label, Icon, status, result };
  });

  return (
    <div className="flex items-stretch gap-0">
      {agents.map((agent, i) => (
        <div key={agent.key} className="flex items-stretch flex-1">
          <AgentStage
            label={agent.label}
            Icon={agent.Icon}
            status={agent.status}
            result={agent.result}
          />
          {i < agents.length - 1 && (
            <div className="flex items-center px-1">
              <Chevron />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function AgentStage({
  label,
  Icon,
  status,
  result,
}: {
  label: string;
  Icon: React.ComponentType<{ className?: string }>;
  status: string;
  result?: AgentResult;
}) {
  const config = getStatusConfig(status);

  return (
    <div
      className={`flex-1 rounded-lg border px-3 py-2.5 ${config.bg} ${config.border}`}
    >
      <div className="flex items-center gap-2">
        <Icon className={`w-3.5 h-3.5 ${config.color}`} />
        <span className="text-xs font-medium">{label}</span>
      </div>
      <div className="mt-1.5 flex items-center gap-1.5">
        <span className={`text-2xs uppercase tracking-wider ${config.color}`}>
          {status}
        </span>
        {result?.error && (
          <span className="text-2xs text-red truncate">{result.error}</span>
        )}
      </div>
    </div>
  );
}

function Chevron() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      className="text-ink-muted"
    >
      <path
        d="M6 4l4 4-4 4"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function getStatusConfig(status: string): {
  bg: string;
  border: string;
  color: string;
} {
  const s = status.toLowerCase();
  if (s === "completed" || s === "success" || s === "ok") {
    return {
      bg: "bg-green-subtle",
      border: "border-green-border",
      color: "text-green",
    };
  }
  if (s === "failed" || s === "error") {
    return {
      bg: "bg-red-subtle",
      border: "border-red-border",
      color: "text-red",
    };
  }
  if (s === "running" || s === "in_progress") {
    return {
      bg: "bg-primary-subtle",
      border: "border-primary-border",
      color: "text-primary",
    };
  }
  return {
    bg: "bg-surface-alt",
    border: "border-border",
    color: "text-ink-tertiary",
  };
}
