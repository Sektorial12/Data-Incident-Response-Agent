import type { RootCause } from "../lib/api";

export function RootCauseList({ causes }: { causes: RootCause[] }) {
  const sorted = [...causes].sort((a, b) => b.confidence - a.confidence);

  return (
    <div className="space-y-2">
      {sorted.map((cause, i) => {
        const urn = cause.candidate_urn || cause.urn || "unknown";
        const name = extractName(urn);
        const confidence = cause.confidence;
        const reason = cause.reasoning || cause.reason || "";
        const level = getConfidenceLevel(confidence);

        return (
          <div
            key={i}
            className="rounded border border-border bg-white px-4 py-3"
          >
            <div className="flex items-center gap-3">
              <span className="text-2xs tabular text-ink-muted w-4">
                {i + 1}
              </span>
              <span className="text-sm font-medium text-ink-primary flex-1 truncate">
                {name}
              </span>
              <span className={`text-2xs uppercase tracking-wider ${level.color}`}>
                {level.label}
              </span>
            </div>
            <div className="mt-2 flex items-center gap-2">
              <div className="flex-1 h-1.5 bg-border rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${level.barColor}`}
                  style={{ width: `${confidence * 100}%` }}
                />
              </div>
              <span className="text-xs tabular font-medium w-10 text-right text-ink-primary">
                {(confidence * 100).toFixed(0)}%
              </span>
            </div>
            {reason && (
              <p className="mt-2 text-2xs text-ink-secondary leading-relaxed">
                {reason}
              </p>
            )}
            <p className="mt-1 text-2xs font-mono text-ink-muted truncate">
              {urn}
            </p>
          </div>
        );
      })}
    </div>
  );
}

function getConfidenceLevel(confidence: number): {
  label: string;
  color: string;
  barColor: string;
} {
  if (confidence >= 0.8) {
    return {
      label: "Confirmed",
      color: "text-green",
      barColor: "bg-green",
    };
  }
  if (confidence >= 0.5) {
    return {
      label: "Probable",
      color: "text-amber",
      barColor: "bg-amber",
    };
  }
  return {
    label: "Low",
    color: "text-ink-tertiary",
    barColor: "bg-ink-muted",
  };
}

function extractName(urn: string): string {
  if (!urn) return "unknown";
  const parts = urn.replace("urn:li:dataset:", "").split(",");
  if (parts.length >= 2) {
    return parts[1].replace(/[()]/g, "").trim();
  }
  return urn;
}
