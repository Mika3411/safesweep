"use client";

import { Laptop, Search } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { allActiveDevices, CustomerLicense, getCustomerLicenses } from "@/lib/customer-api";
import { formatDate } from "@/lib/format";
import { EmptyState, ErrorState, LoadingState } from "@/components/customer/CustomerStates";
import { DeactivateDeviceButton } from "@/components/customer/LicenseActions";

export function CustomerDevicesView() {
  const [licenses, setLicenses] = useState<CustomerLicense[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);

    try {
      setLicenses(await getCustomerLicenses());
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Chargement impossible.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const devices = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const items = allActiveDevices(licenses);

    if (!needle) {
      return items;
    }

    return items.filter(
      (device) =>
        device.name.toLowerCase().includes(needle) ||
        device.licensePublicId.toLowerCase().includes(needle) ||
        device.product.toLowerCase().includes(needle)
    );
  }, [licenses, query]);

  if (loading) {
    return <LoadingState label="Chargement des appareils..." />;
  }

  if (error) {
    return <ErrorState message={error} onRetry={load} />;
  }

  return (
    <main className="customer-page">
      <section className="main-panel">
        <div className="panel-heading">
          <h2>Mes appareils actives</h2>
          <label className="search-box">
            <Search size={16} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Rechercher un appareil..." />
          </label>
        </div>

        {devices.length === 0 ? (
          <EmptyState title="Aucun appareil actif" description="Les appareils actives apparaitront apres validation d'une licence." />
        ) : (
          <div className="device-grid">
            {devices.map((device) => (
              <article className="device-card" key={device.id}>
                <Laptop size={18} />
                <div>
                  <strong>{device.name}</strong>
                  <small>{device.platform ?? "Poste de travail"}</small>
                  <Link href={`/licenses/${device.licenseId}`}>{device.licensePublicId}</Link>
                </div>
                <span>Derniere activite: {formatDate(device.lastSeenAt ?? device.activatedAt)}</span>
                <DeactivateDeviceButton licenseId={device.licenseId} deviceId={device.id} onDone={load} />
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
