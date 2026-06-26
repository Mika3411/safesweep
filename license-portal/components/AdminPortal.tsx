"use client";

import {
  CalendarDays,
  CheckCircle2,
  Filter,
  KeyRound,
  Laptop,
  Plus,
  Search,
  ShieldOff,
  Webhook
} from "lucide-react";
import { FormEvent, useMemo, useState } from "react";
import { formatCurrency, formatDate, formatDateTime, productLabel } from "@/lib/format";
import {
  PortalCustomer,
  PortalLicense,
  PortalPayment,
  PortalStripeWebhookEvent,
  PortalValidation
} from "@/lib/portal-types";
import { AppShell } from "@/components/AppShell";
import { StatusBadge } from "@/components/StatusBadge";

type AdminPortalProps = {
  userName: string;
  customers: PortalCustomer[];
  licenses: PortalLicense[];
  validations: PortalValidation[];
  payments: PortalPayment[];
  stripeWebhookEvents?: PortalStripeWebhookEvent[];
  demo?: boolean;
};

export function AdminPortal({
  userName,
  customers,
  licenses,
  validations,
  payments,
  stripeWebhookEvents = [],
  demo = false
}: AdminPortalProps) {
  const [licenseItems, setLicenseItems] = useState(licenses);
  const [selectedId, setSelectedId] = useState(licenses[0]?.id);
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const selected = licenseItems.find((license) => license.id === selectedId) ?? licenseItems[0];

  const linkedDevices = useMemo(() => selected?.devices ?? [], [selected]);

  async function updateStatus(status: "ACTIVE" | "SUSPENDED" | "REVOKED") {
    if (!selected) {
      return;
    }

    if (!demo) {
      const response = await fetch(`/api/admin/licenses/${selected.id}/status`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status })
      });

      if (!response.ok) {
        alert("Action impossible.");
        return;
      }
    }

    setLicenseItems((current) =>
      current.map((license) => (license.id === selected.id ? { ...license, status } : license))
    );
  }

  async function extendExpiration() {
    if (!selected) {
      return;
    }

    const nextDate = new Date(selected.expiresAt);
    nextDate.setFullYear(nextDate.getFullYear() + 1);

    if (!demo) {
      const response = await fetch(`/api/admin/licenses/${selected.id}/expiration`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expiresAt: nextDate.toISOString() })
      });

      if (!response.ok) {
        alert("Modification impossible.");
        return;
      }
    }

    setLicenseItems((current) =>
      current.map((license) =>
        license.id === selected.id ? { ...license, expiresAt: nextDate.toISOString(), status: "ACTIVE" } : license
      )
    );
  }

  async function createLicense(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const payload = {
      userId: String(form.get("userId")),
      product: String(form.get("product")),
      deviceLimit: Number(form.get("deviceLimit")),
      seatCount: Number(form.get("seatCount")),
      expiresAt: new Date(String(form.get("expiresAt"))).toISOString()
    };

    if (demo) {
      setCreatedKey("DEMO-KEY9-PORT-AL26");
      return;
    }

    const response = await fetch("/api/admin/licenses", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = (await response.json()) as { rawKey?: string; license?: PortalLicense; error?: string };

    if (!response.ok || !data.license) {
      alert(data.error ?? "Creation impossible.");
      return;
    }

    setLicenseItems((current) => [data.license!, ...current]);
    setSelectedId(data.license.id);
    setCreatedKey(data.rawKey ?? null);
  }

  return (
    <AppShell mode="admin" title="Gestion des licences" userName={userName} userRole="Administrateur">
      <main className="admin-grid">
        <section className="admin-panel" id="customers">
          <div className="panel-heading compact">
            <h2>Clients</h2>
            <label className="search-box small">
              <Search size={14} />
              <input placeholder="Rechercher un client..." />
            </label>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Client</th>
                  <th>E-mail</th>
                  <th>Licences</th>
                  <th>Statut</th>
                </tr>
              </thead>
              <tbody>
                {customers.map((customer) => (
                  <tr key={customer.id}>
                    <td>{customer.company ?? customer.name}</td>
                    <td>{customer.email}</td>
                    <td>{customer.licenseCount}</td>
                    <td>
                      <StatusBadge status={customer.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="admin-panel wide" id="licenses">
          <div className="panel-heading compact">
            <h2>Toutes les licences</h2>
            <div className="table-tools">
              <label className="search-box small">
                <Search size={14} />
                <input placeholder="Rechercher une licence..." />
              </label>
              <button className="icon-button" type="button" aria-label="Filtrer">
                <Filter size={15} />
              </button>
            </div>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Licence</th>
                  <th>Client</th>
                  <th>Produit</th>
                  <th>Statut</th>
                  <th>Expiration</th>
                </tr>
              </thead>
              <tbody>
                {licenseItems.map((license) => (
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
                    <td>{license.owner?.company ?? "Acme Industries"}</td>
                    <td>{productLabel(license.product).replace("SafeSweep ", "")}</td>
                    <td>
                      <StatusBadge status={license.status} />
                    </td>
                    <td>{formatDate(license.expiresAt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="admin-panel form-panel">
          <h2>Creer une licence</h2>
          <form className="license-form" onSubmit={createLicense}>
            <label>
              Client
              <select name="userId" required>
                {customers.map((customer) => (
                  <option key={customer.id} value={customer.id}>
                    {customer.company ?? customer.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Produit
              <select name="product" required defaultValue="ENDPOINT">
                <option value="ENDPOINT">Endpoint</option>
                <option value="SERVER">Server</option>
                <option value="MOBILE">Mobile</option>
              </select>
            </label>
            <div className="form-row">
              <label>
                Sieges
                <input name="seatCount" type="number" min={1} defaultValue={10} />
              </label>
              <label>
                Appareils
                <input name="deviceLimit" type="number" min={1} defaultValue={10} />
              </label>
            </div>
            <label>
              Expiration
              <input name="expiresAt" type="date" defaultValue="2027-06-25" />
            </label>
            <button className="primary-button" type="submit">
              <Plus size={16} />
              Creer la licence
            </button>
          </form>
          {createdKey ? <p className="created-key">Cle creee: {createdKey}</p> : null}
        </section>

        <section className="admin-panel actions-panel">
          <h2>Actions rapides</h2>
          <button className="secondary-button" type="button" onClick={extendExpiration}>
            <CalendarDays size={16} />
            Prolonger l'expiration
          </button>
          <button className="secondary-button danger-soft" type="button" onClick={() => updateStatus("SUSPENDED")}>
            <ShieldOff size={16} />
            Suspendre la licence
          </button>
          <button className="secondary-button danger" type="button" onClick={() => updateStatus("REVOKED")}>
            <ShieldOff size={16} />
            Revoquer la licence
          </button>
          <button className="secondary-button success" type="button" onClick={() => updateStatus("ACTIVE")}>
            <CheckCircle2 size={16} />
            Reactiver la licence
          </button>
        </section>

        <section className="admin-panel devices-panel" id="devices">
          <h2>Appareils lies ({linkedDevices.length})</h2>
          <div className="device-list">
            {linkedDevices.map((device) => (
              <div className="device-row" key={device.id}>
                <Laptop size={16} />
                <span>
                  <strong>{device.name}</strong>
                  <small>{device.deactivatedAt ? "Inactif" : "Actif"}</small>
                </span>
                <small>{formatDate(device.lastSeenAt ?? device.activatedAt)}</small>
              </div>
            ))}
          </div>
        </section>

        <section className="admin-panel wide-bottom" id="validations">
          <h2>Historique des validations</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Action</th>
                  <th>Licence</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {validations.map((validation) => (
                  <tr key={validation.id}>
                    <td>{formatDateTime(validation.createdAt)}</td>
                    <td>{validation.action}</td>
                    <td>{validation.licensePublicId ?? "-"}</td>
                    <td>{validation.reason ?? validation.deviceName ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="admin-panel wide-bottom payments-panel" id="payments">
          <h2>Paiements recents</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Client</th>
                  <th>Facture</th>
                  <th>Montant</th>
                  <th>Statut</th>
                  <th>Methode</th>
                </tr>
              </thead>
              <tbody>
                {payments.map((payment) => (
                  <tr key={payment.id}>
                    <td>{formatDate(payment.createdAt)}</td>
                    <td>{payment.client}</td>
                    <td>{payment.invoice ?? "-"}</td>
                    <td>{formatCurrency(payment.amountCents, payment.currency)}</td>
                    <td>
                      <StatusBadge status={payment.status} />
                    </td>
                    <td>{payment.method ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="admin-panel wide-bottom webhooks-panel" id="stripe-webhooks">
          <div className="panel-heading compact">
            <h2>Webhooks Stripe</h2>
            <Webhook size={16} />
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Derniere reception</th>
                  <th>Event ID</th>
                  <th>Type</th>
                  <th>Statut</th>
                  <th>Receptions</th>
                  <th>Erreur</th>
                </tr>
              </thead>
              <tbody>
                {stripeWebhookEvents.map((event) => (
                  <tr key={event.id}>
                    <td>{formatDateTime(event.lastReceivedAt)}</td>
                    <td>{event.eventId}</td>
                    <td>{event.type}</td>
                    <td>
                      <StatusBadge status={event.status} />
                    </td>
                    <td>{event.receivedCount}</td>
                    <td>{event.error ?? "-"}</td>
                  </tr>
                ))}
                {stripeWebhookEvents.length === 0 ? (
                  <tr>
                    <td colSpan={6}>Aucun webhook Stripe recu.</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>
      </main>
    </AppShell>
  );
}
