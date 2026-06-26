"use client";

import { CreditCard, Download, Power, RefreshCw, ShoppingCart } from "lucide-react";
import { useState } from "react";
import { apiFetch } from "@/lib/customer-api";

type ProductCode = "ENDPOINT" | "SERVER" | "MOBILE";

export function DownloadButton({ compact = false }: { compact?: boolean }) {
  return (
    <a className={compact ? "secondary-button" : "primary-button"} href="/api/downloads/software">
      <Download size={16} />
      Telecharger
    </a>
  );
}

export function RenewButton({ licenseId }: { licenseId: string }) {
  const [loading, setLoading] = useState(false);

  async function renew() {
    setLoading(true);

    try {
      const data = await apiFetch<{ url?: string }>("/api/billing/checkout", {
        method: "POST",
        body: JSON.stringify({ licenseId })
      });

      if (data.url) {
        window.location.href = data.url;
      }
    } catch (error) {
      alert(error instanceof Error ? error.message : "Renouvellement indisponible.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <button className="outline-accent-button" type="button" onClick={renew} disabled={loading}>
      <RefreshCw size={16} />
      {loading ? "Ouverture..." : "Renouveler"}
    </button>
  );
}

export function BuyLicenseButton({
  product = "ENDPOINT",
  maxActivations = 3,
  seatCount = maxActivations,
  compact = false
}: {
  product?: ProductCode;
  maxActivations?: number;
  seatCount?: number;
  compact?: boolean;
}) {
  const [loading, setLoading] = useState(false);

  async function buy() {
    setLoading(true);

    try {
      const data = await apiFetch<{ url?: string }>("/api/billing/checkout", {
        method: "POST",
        body: JSON.stringify({ product, maxActivations, seatCount })
      });

      if (data.url) {
        window.location.href = data.url;
      }
    } catch (error) {
      alert(error instanceof Error ? error.message : "Achat indisponible.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <button className={compact ? "secondary-button" : "primary-button"} type="button" onClick={buy} disabled={loading}>
      <ShoppingCart size={16} />
      {loading ? "Ouverture..." : "Acheter une licence"}
    </button>
  );
}

export function BillingPortalButton() {
  const [loading, setLoading] = useState(false);

  async function openPortal() {
    setLoading(true);

    try {
      const data = await apiFetch<{ url?: string }>("/api/billing/portal", {
        method: "POST"
      });

      if (data.url) {
        window.location.href = data.url;
      }
    } catch (error) {
      alert(error instanceof Error ? error.message : "Portail de facturation indisponible.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <button className="secondary-button" type="button" onClick={openPortal} disabled={loading}>
      <CreditCard size={16} />
      {loading ? "Ouverture..." : "Gerer la facturation"}
    </button>
  );
}

export function DeactivateDeviceButton({
  licenseId,
  deviceId,
  onDone
}: {
  licenseId: string;
  deviceId: string;
  onDone: () => void;
}) {
  const [loading, setLoading] = useState(false);

  async function deactivate() {
    setLoading(true);

    try {
      await apiFetch(`/api/licenses/${licenseId}/devices/${deviceId}`, { method: "DELETE" });
      onDone();
    } catch (error) {
      alert(error instanceof Error ? error.message : "Desactivation impossible.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <button className="tiny-button" type="button" onClick={deactivate} disabled={loading}>
      <Power size={13} />
      {loading ? "..." : "Desactiver"}
    </button>
  );
}
