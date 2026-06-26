"use client";

import { AlertCircle, Inbox, Loader2 } from "lucide-react";

export function LoadingState({ label = "Chargement..." }: { label?: string }) {
  return (
    <div className="state-panel">
      <Loader2 className="spin" size={20} />
      <strong>{label}</strong>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="state-panel state-error">
      <AlertCircle size={20} />
      <strong>{message}</strong>
      {onRetry ? (
        <button className="secondary-button" type="button" onClick={onRetry}>
          Reessayer
        </button>
      ) : null}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty-state">
      <Inbox size={22} />
      <strong>{title}</strong>
      <p>{description}</p>
      {action}
    </div>
  );
}
