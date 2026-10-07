import type { Recording } from "../api/types";

const LABELS: Record<Recording["status"], string> = {
  queued: "Queued",
  processing: "Processing",
  ready: "Ready",
  failed: "Failed",
};

export function StatusChip({ status }: { status: Recording["status"] }) {
  return (
    <span className={`chip chip-${status}`}>
      {status === "processing" && <span className="dot-pulse" />}
      {LABELS[status]}
    </span>
  );
}
