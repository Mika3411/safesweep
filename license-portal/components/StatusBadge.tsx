import { statusLabel } from "@/lib/format";

type StatusBadgeProps = {
  status: string;
};

export function StatusBadge({ status }: StatusBadgeProps) {
  const normalized = status.toLowerCase();
  const labelKey = status.toUpperCase();

  return <span className={`status-badge status-${normalized}`}>{statusLabel(labelKey)}</span>;
}
