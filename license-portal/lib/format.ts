export function formatDate(value: string | Date | null | undefined) {
  if (!value) {
    return "-";
  }

  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric"
  }).format(new Date(value));
}

export function formatDateTime(value: string | Date | null | undefined) {
  if (!value) {
    return "-";
  }

  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

export function formatCurrency(cents: number, currency = "eur") {
  return new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency: currency.toUpperCase()
  }).format(cents / 100);
}

export function productLabel(product: string) {
  const labels: Record<string, string> = {
    ENDPOINT: "SafeSweep Endpoint",
    SERVER: "SafeSweep Server",
    MOBILE: "SafeSweep Mobile"
  };

  return labels[product] ?? product;
}

export function statusLabel(status: string) {
  const labels: Record<string, string> = {
    ACTIVE: "Active",
    EXPIRED: "Expiree",
    SUSPENDED: "Suspendue",
    REVOKED: "Revoquee",
    PAID: "Paye",
    PENDING: "En attente",
    PROCESSING: "En cours",
    PROCESSED: "Traite",
    FAILED: "Echoue",
    DENIED: "Refuse",
    paid: "Paye",
    pending: "En attente",
    failed: "Echoue"
  };

  return labels[status] ?? status;
}
