"use client";

import { Copy, Eye, KeyRound, Laptop } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { apiFetch, CustomerLicense, getCustomerLicense } from "@/lib/customer-api";
import { formatCurrency, formatDate } from "@/lib/format";
import { EmptyState, ErrorState, LoadingState } from "@/components/customer/CustomerStates";
import { DeactivateDeviceButton, DownloadButton, RenewButton } from "@/components/customer/LicenseActions";
import { StatusBadge } from "@/components/StatusBadge";

function maskedKey(prefix: string) {
  return `${prefix || "XXXX"}-XXXX-XXXX-XXXX`;
}

export function CustomerLicenseDetailView({ licenseId }: { licenseId: string }) {
  const [license, setLicense] = useState<CustomerLicense | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [revealedKey, setRevealedKey] = useState<string | null>(null);
  const [revealing, setRevealing] = useState(false);
  const [revealError, setRevealError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);

    try {
      setLicense(await getCustomerLicense(licenseId));
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Chargement impossible.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [licenseId]);

  async function revealLicenseKey() {
    if (!license) {
      return;
    }

    setRevealing(true);
    setRevealError(null);

    try {
      const data = await apiFetch<{ licenseKey: string; revealedAt: string }>(
        `/api/customer/licenses/${license.id}/reveal`,
        { method: "POST" }
      );

      setRevealedKey(data.licenseKey);
      setLicense({
        ...license,
        licenseKeyAvailable: false,
        licenseKeyRevealedAt: data.revealedAt
      });
      await navigator.clipboard?.writeText(data.licenseKey).catch(() => undefined);
    } catch (nextError) {
      setRevealError(nextError instanceof Error ? nextError.message : "Cle indisponible.");
    } finally {
      setRevealing(false);
    }
  }

  if (loading) {
    return <LoadingState label="Chargement de la licence..." />;
  }

  if (error) {
    return <ErrorState message={error} onRetry={load} />;
  }

  if (!license) {
    return <EmptyState title="Licence introuvable" description="Cette licence n'existe pas ou n'est pas rattachee a votre compte." />;
  }

  const activeDevices = license.devices.filter((device) => !device.deactivatedAt);

  return (
    <main className="portal-grid">
      <section className="main-panel">
        <div className="detail-heading">
          <h2>{license.publicId}</h2>
          <StatusBadge status={license.status} />
        </div>

        <dl className="detail-list detail-list-wide">
          <div>
            <dt>Produit</dt>
            <dd>{license.product}</dd>
          </div>
          <div>
            <dt>Expiration</dt>
            <dd>{formatDate(license.expiresAt)}</dd>
          </div>
          <div>
            <dt>Appareils actives</dt>
            <dd>
              {license.activeActivations} / {license.maxActivations}
            </dd>
          </div>
          <div>
            <dt>Activations restantes</dt>
            <dd>{license.remainingActivations}</dd>
          </div>
          <div>
            <dt>Sieges</dt>
            <dd>{license.seats}</dd>
          </div>
          <div>
            <dt>Cle</dt>
            <dd>{revealedKey ?? maskedKey(license.keyPrefix)}</dd>
          </div>
        </dl>

        <div className="usage-bar" aria-hidden="true">
          <span style={{ width: `${Math.min((license.activeActivations / license.maxActivations) * 100, 100)}%` }} />
        </div>

        <div className="detail-actions detail-actions-inline">
          <DownloadButton />
          <RenewButton licenseId={license.id} />
          <button className="secondary-button" type="button" onClick={() => navigator.clipboard?.writeText(license.publicId)}>
            <Copy size={16} />
            Copier la reference
          </button>
        </div>

        {license.licenseKeyAvailable || revealedKey || revealError ? (
          <section className="mini-section license-key-section">
            <div className="panel-heading">
              <h3>Cle de licence</h3>
              <KeyRound size={18} />
            </div>
            {revealedKey ? (
              <div className="license-key-reveal">
                <code>{revealedKey}</code>
                <button className="secondary-button" type="button" onClick={() => navigator.clipboard?.writeText(revealedKey)}>
                  <Copy size={16} />
                  Copier
                </button>
              </div>
            ) : (
              <button className="outline-accent-button" type="button" onClick={revealLicenseKey} disabled={revealing}>
                <Eye size={16} />
                {revealing ? "Revelation..." : "Reveler la cle"}
              </button>
            )}
            {revealError ? <p className="form-error">{revealError}</p> : null}
          </section>
        ) : null}

        <section className="mini-section">
          <div className="panel-heading">
            <h3>Appareils actives</h3>
            <Link className="secondary-button" href="/devices">
              Tout gerer
            </Link>
          </div>
          {activeDevices.length === 0 ? (
            <EmptyState title="Aucun appareil" description="Aucun poste actif n'utilise actuellement cette licence." />
          ) : (
            <div className="device-list">
              {activeDevices.map((device) => (
                <div className="device-row" key={device.id}>
                  <Laptop size={16} />
                  <span>
                    <strong>{device.name}</strong>
                    <small>{device.platform ?? "Poste de travail"} - vu le {formatDate(device.lastSeenAt ?? device.activatedAt)}</small>
                  </span>
                  <DeactivateDeviceButton licenseId={license.id} deviceId={device.id} onDone={load} />
                </div>
              ))}
            </div>
          )}
        </section>
      </section>

      <aside className="detail-panel">
        <h2>Factures associees</h2>
        <div className="invoice-list">
          {license.invoices.map((invoice) => (
            <Link className="invoice-row" href={invoice.invoicePdfUrl ?? "/invoices"} key={invoice.id}>
              <span>{invoice.number}</span>
              <strong>{formatCurrency(invoice.amountCents, invoice.currency)}</strong>
              <small>{formatDate(invoice.paidAt ?? invoice.createdAt)}</small>
            </Link>
          ))}
          {license.invoices.length === 0 ? <p className="muted-copy">Aucune facture associee.</p> : null}
        </div>
      </aside>
    </main>
  );
}
