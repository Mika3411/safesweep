"use client";

import { CalendarDays, KeyRound, Laptop, Power, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { getCustomerInvoices, getCustomerLicenses, activeDevices, CustomerLicense } from "@/lib/customer-api";
import { formatCurrency, formatDate } from "@/lib/format";
import { PortalInvoice } from "@/lib/portal-types";
import { EmptyState, ErrorState, LoadingState } from "@/components/customer/CustomerStates";
import { BuyLicenseButton, DownloadButton } from "@/components/customer/LicenseActions";
import { StatusBadge } from "@/components/StatusBadge";

export function CustomerDashboardView() {
  const [licenses, setLicenses] = useState<CustomerLicense[]>([]);
  const [invoices, setInvoices] = useState<PortalInvoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);

    try {
      const [nextLicenses, nextInvoices] = await Promise.all([getCustomerLicenses(), getCustomerInvoices()]);
      setLicenses(nextLicenses);
      setInvoices(nextInvoices);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Chargement impossible.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const totals = useMemo(
    () => ({
      all: licenses.length,
      active: licenses.filter((license) => license.status === "active").length,
      expired: licenses.filter((license) => license.status === "expired").length,
      suspended: licenses.filter((license) => license.status === "suspended").length,
      revoked: licenses.filter((license) => license.status === "revoked").length,
      devices: licenses.reduce((sum, license) => sum + activeDevices(license).length, 0),
      maxDevices: licenses.reduce((sum, license) => sum + license.maxActivations, 0)
    }),
    [licenses]
  );

  if (loading) {
    return <LoadingState label="Chargement du tableau de bord..." />;
  }

  if (error) {
    return <ErrorState message={error} onRetry={load} />;
  }

  return (
    <main className="customer-page">
      <section className="summary-grid">
        <SummaryTile icon={<KeyRound size={20} />} label="Licences totales" value={totals.all} />
        <SummaryTile icon={<ShieldCheck size={20} />} label="Actives" value={totals.active} tone="green" />
        <SummaryTile icon={<CalendarDays size={20} />} label="Expirees" value={totals.expired} tone="amber" />
        <SummaryTile icon={<Power size={20} />} label="Suspendues" value={totals.suspended} tone="orange" />
        <SummaryTile icon={<Power size={20} />} label="Revoquees" value={totals.revoked} tone="red" />
        <SummaryTile icon={<Laptop size={20} />} label="Appareils" value={`${totals.devices} / ${totals.maxDevices}`} tone="blue" />
      </section>

      <section className="customer-grid">
        <article className="main-panel">
          <div className="panel-heading">
            <h2>Licences recentes</h2>
            <Link className="secondary-button" href="/licenses">
              Voir tout
            </Link>
          </div>
          {licenses.length === 0 ? (
            <EmptyState
              title="Aucune licence"
              description="Vos licences apparaitront ici apres achat ou attribution par un administrateur."
            />
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Licence</th>
                    <th>Produit</th>
                    <th>Statut</th>
                    <th>Expiration</th>
                    <th>Appareils</th>
                  </tr>
                </thead>
                <tbody>
                  {licenses.slice(0, 5).map((license) => (
                    <tr key={license.id}>
                      <td>
                        <Link className="text-link" href={`/licenses/${license.id}`}>
                          {license.publicId}
                        </Link>
                      </td>
                      <td>{license.product}</td>
                      <td>
                        <StatusBadge status={license.status} />
                      </td>
                      <td>{formatDate(license.expiresAt)}</td>
                      <td>
                        {license.activeActivations} / {license.maxActivations}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </article>

        <aside className="detail-panel">
          <h2>Acces rapide</h2>
          <div className="quick-actions">
            <BuyLicenseButton />
            <DownloadButton />
            <Link className="secondary-button" href="/devices">
              <Laptop size={16} />
              Gerer les appareils
            </Link>
            <Link className="secondary-button" href="/invoices">
              Factures
            </Link>
          </div>
          <section className="mini-section">
            <h3>Dernieres factures</h3>
            <div className="invoice-list">
              {invoices.slice(0, 3).map((invoice) => (
                <Link className="invoice-row" href={invoice.invoicePdfUrl ?? "/invoices"} key={invoice.id}>
                  <span>{invoice.number}</span>
                  <strong>{formatCurrency(invoice.amountCents, invoice.currency)}</strong>
                  <small>{formatDate(invoice.paidAt ?? invoice.createdAt)}</small>
                </Link>
              ))}
              {invoices.length === 0 ? <p className="muted-copy">Aucune facture pour le moment.</p> : null}
            </div>
          </section>
        </aside>
      </section>
    </main>
  );
}

function SummaryTile({
  icon,
  label,
  value,
  tone = "teal"
}: {
  icon: React.ReactNode;
  label: string;
  value: number | string;
  tone?: "teal" | "green" | "amber" | "orange" | "red" | "blue";
}) {
  return (
    <article className={`summary-tile tone-${tone}`}>
      <span>{icon}</span>
      <div>
        <small>{label}</small>
        <strong>{value}</strong>
      </div>
    </article>
  );
}
