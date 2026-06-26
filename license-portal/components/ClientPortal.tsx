"use client";

import {
  CalendarDays,
  ChevronRight,
  Copy,
  Download,
  Filter,
  KeyRound,
  Laptop,
  Power,
  ReceiptText,
  RefreshCw,
  Search,
  ShieldCheck
} from "lucide-react";
import { useMemo, useState } from "react";
import { formatCurrency, formatDate, productLabel } from "@/lib/format";
import { PortalInvoice, PortalLicense } from "@/lib/portal-types";
import { AppShell } from "@/components/AppShell";
import { StatusBadge } from "@/components/StatusBadge";

type ClientPortalProps = {
  userName: string;
  company?: string | null;
  licenses: PortalLicense[];
  invoices: PortalInvoice[];
  demo?: boolean;
};

function activeDeviceCount(license: PortalLicense) {
  return license.devices.filter((device) => !device.deactivatedAt).length;
}

function maskedKey(prefix: string) {
  return `${prefix || "XXXX"}-XXXX-XXXX-XXXX`;
}

export function ClientPortal({ userName, company, licenses, invoices, demo = false }: ClientPortalProps) {
  const [items, setItems] = useState(licenses);
  const [selectedId, setSelectedId] = useState(licenses[0]?.id);
  const [query, setQuery] = useState("");
  const selected = items.find((license) => license.id === selectedId) ?? items[0];

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();

    if (!needle) {
      return items;
    }

    return items.filter(
      (license) =>
        license.publicId.toLowerCase().includes(needle) ||
        productLabel(license.product).toLowerCase().includes(needle) ||
        license.status.toLowerCase().includes(needle)
    );
  }, [items, query]);

  const totals = useMemo(
    () => ({
      all: items.length,
      active: items.filter((license) => license.status === "ACTIVE").length,
      expired: items.filter((license) => license.status === "EXPIRED").length,
      suspended: items.filter((license) => license.status === "SUSPENDED").length,
      revoked: items.filter((license) => license.status === "REVOKED").length,
      devices: items.reduce((sum, license) => sum + activeDeviceCount(license), 0),
      deviceLimit: items.reduce((sum, license) => sum + license.deviceLimit, 0)
    }),
    [items]
  );

  async function deactivateDevice(deviceId: string) {
    if (!selected) {
      return;
    }

    if (!demo) {
      const response = await fetch(`/api/licenses/${selected.id}/devices/${deviceId}`, {
        method: "DELETE"
      });

      if (!response.ok) {
        alert("Impossible de desactiver cet appareil.");
        return;
      }
    }

    setItems((current) =>
      current.map((license) =>
        license.id === selected.id
          ? {
              ...license,
              devices: license.devices.map((device) =>
                device.id === deviceId ? { ...device, deactivatedAt: new Date().toISOString() } : device
              )
            }
          : license
      )
    );
  }

  async function renewLicense() {
    if (!selected || demo) {
      return;
    }

    const response = await fetch("/api/billing/checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ licenseId: selected.id })
    });
    const data = (await response.json()) as { url?: string; error?: string };

    if (data.url) {
      window.location.href = data.url;
    } else {
      alert(data.error ?? "Renouvellement indisponible.");
    }
  }

  return (
    <AppShell
      mode="client"
      title="Tableau de bord"
      userName={company ?? userName}
      userRole="Client"
    >
      <main className="portal-grid">
        <section className="main-panel" id="licenses">
          <div className="summary-grid">
            <SummaryTile icon={<KeyRound size={20} />} label="Licences totales" value={totals.all} />
            <SummaryTile icon={<ShieldCheck size={20} />} label="Actives" value={totals.active} tone="green" />
            <SummaryTile icon={<CalendarDays size={20} />} label="Expirees" value={totals.expired} tone="amber" />
            <SummaryTile icon={<Power size={20} />} label="Suspendues" value={totals.suspended} tone="orange" />
            <SummaryTile icon={<Power size={20} />} label="Revoquees" value={totals.revoked} tone="red" />
            <SummaryTile
              icon={<Laptop size={20} />}
              label="Appareils actives"
              value={`${totals.devices} / ${totals.deviceLimit}`}
              tone="blue"
            />
          </div>

          <div className="panel-heading">
            <h2>Mes licences</h2>
            <div className="table-tools">
              <label className="search-box">
                <Search size={16} />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Rechercher une licence..."
                />
              </label>
              <button className="secondary-button" type="button">
                <Filter size={15} />
                Filtrer
              </button>
            </div>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Licence</th>
                  <th>Produit</th>
                  <th>Statut</th>
                  <th>Expiration</th>
                  <th>Appareils actives</th>
                  <th>Sieges</th>
                  <th>Prochain renouvellement</th>
                  <th aria-label="Selection" />
                </tr>
              </thead>
              <tbody>
                {filtered.map((license) => (
                  <tr
                    className={license.id === selected?.id ? "selected-row" : ""}
                    key={license.id}
                    onClick={() => setSelectedId(license.id)}
                  >
                    <td>
                      <button className="text-link" type="button">
                        {license.publicId}
                      </button>
                    </td>
                    <td>{productLabel(license.product)}</td>
                    <td>
                      <StatusBadge status={license.status} />
                    </td>
                    <td>{formatDate(license.expiresAt)}</td>
                    <td>
                      {activeDeviceCount(license)} / {license.deviceLimit}
                    </td>
                    <td>{license.seatCount}</td>
                    <td>{license.status === "ACTIVE" ? formatDate(license.expiresAt) : "-"}</td>
                    <td>
                      <ChevronRight size={16} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {selected ? (
          <aside className="detail-panel">
            <div className="detail-heading">
              <h2>Details de la licence</h2>
              <StatusBadge status={selected.status} />
            </div>

            <div className="detail-title">
              <strong>{selected.publicId}</strong>
              <button className="icon-button" type="button" aria-label="Copier la reference">
                <Copy size={15} />
              </button>
            </div>

            <dl className="detail-list">
              <div>
                <dt>Produit</dt>
                <dd>{productLabel(selected.product)}</dd>
              </div>
              <div>
                <dt>Cle de licence</dt>
                <dd>{maskedKey(selected.keyPrefix)}</dd>
              </div>
              <div>
                <dt>Expiration</dt>
                <dd>{formatDate(selected.expiresAt)}</dd>
              </div>
              <div>
                <dt>Sieges</dt>
                <dd>{selected.seatCount}</dd>
              </div>
              <div>
                <dt>Appareils actives</dt>
                <dd>
                  {activeDeviceCount(selected)} / {selected.deviceLimit}
                </dd>
              </div>
            </dl>

            <div className="usage-bar" aria-hidden="true">
              <span style={{ width: `${Math.min((activeDeviceCount(selected) / selected.deviceLimit) * 100, 100)}%` }} />
            </div>

            <div className="detail-actions" id="billing">
              <a className="primary-button" href="/api/downloads/software">
                <Download size={16} />
                Telecharger le logiciel
              </a>
              <button className="secondary-button" type="button">
                <Laptop size={16} />
                Voir les appareils ({activeDeviceCount(selected)})
              </button>
              <button
                className="secondary-button"
                type="button"
                onClick={() => selected.devices[0] && deactivateDevice(selected.devices[0].id)}
              >
                <Power size={16} />
                Desactiver un appareil
              </button>
              <button className="outline-accent-button" type="button" onClick={renewLicense}>
                <RefreshCw size={16} />
                Renouveler l'abonnement
              </button>
            </div>

            <section className="mini-section" id="devices">
              <h3>Appareils lies</h3>
              <div className="device-list">
                {selected.devices.map((device) => (
                  <div className="device-row" key={device.id}>
                    <Laptop size={16} />
                    <span>
                      <strong>{device.name}</strong>
                      <small>{device.platform ?? "Poste de travail"}</small>
                    </span>
                    <button
                      className="tiny-button"
                      type="button"
                      disabled={Boolean(device.deactivatedAt)}
                      onClick={() => deactivateDevice(device.id)}
                    >
                      {device.deactivatedAt ? "Inactif" : "Desactiver"}
                    </button>
                  </div>
                ))}
              </div>
            </section>

            <section className="mini-section" id="invoices">
              <h3>Factures associees</h3>
              <div className="invoice-list">
                {(selected.invoices.length ? selected.invoices : invoices).slice(0, 4).map((invoice) => (
                  <a className="invoice-row" href={invoice.invoicePdfUrl ?? "#"} key={invoice.id}>
                    <ReceiptText size={15} />
                    <span>{invoice.number}</span>
                    <strong>{formatCurrency(invoice.amountCents, invoice.currency)}</strong>
                    <small>{formatDate(invoice.paidAt ?? invoice.createdAt)}</small>
                  </a>
                ))}
              </div>
            </section>
          </aside>
        ) : null}
      </main>
    </AppShell>
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
