"use client";

import { ChevronRight, Filter, KeyRound, Search } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { CustomerLicense, getCustomerLicenses } from "@/lib/customer-api";
import { formatDate } from "@/lib/format";
import { EmptyState, ErrorState, LoadingState } from "@/components/customer/CustomerStates";
import { BuyLicenseButton, DownloadButton, RenewButton } from "@/components/customer/LicenseActions";
import { StatusBadge } from "@/components/StatusBadge";

export function CustomerLicensesView() {
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

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();

    if (!needle) {
      return licenses;
    }

    return licenses.filter(
      (license) =>
        license.publicId.toLowerCase().includes(needle) ||
        license.product.toLowerCase().includes(needle) ||
        license.status.toLowerCase().includes(needle)
    );
  }, [licenses, query]);

  if (loading) {
    return <LoadingState label="Chargement des licences..." />;
  }

  if (error) {
    return <ErrorState message={error} onRetry={load} />;
  }

  return (
    <main className="customer-page">
      <section className="main-panel">
        <div className="panel-heading">
          <h2>Mes licences</h2>
          <div className="table-tools">
            <BuyLicenseButton compact />
            <label className="search-box">
              <Search size={16} />
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Rechercher..." />
            </label>
            <button className="secondary-button" type="button">
              <Filter size={15} />
              Filtrer
            </button>
          </div>
        </div>

        {licenses.length === 0 ? (
          <EmptyState
            title="Aucune licence"
            description="Vous n'avez pas encore de licence rattachee a ce compte."
            action={<BuyLicenseButton />}
          />
        ) : filtered.length === 0 ? (
          <EmptyState title="Aucun resultat" description="Essayez une autre recherche ou effacez le filtre." />
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
                  <th>Actions</th>
                  <th aria-label="Detail" />
                </tr>
              </thead>
              <tbody>
                {filtered.map((license) => (
                  <tr key={license.id}>
                    <td>
                      <Link className="text-link" href={`/licenses/${license.id}`}>
                        {license.publicId}
                      </Link>
                      {license.licenseKeyAvailable ? (
                        <span className="inline-license-alert">
                          <KeyRound size={13} />
                          Cle disponible
                        </span>
                      ) : null}
                    </td>
                    <td>{license.product}</td>
                    <td>
                      <StatusBadge status={license.status} />
                    </td>
                    <td>{formatDate(license.expiresAt)}</td>
                    <td>
                      {license.activeActivations} / {license.maxActivations}
                    </td>
                    <td>
                      <div className="row-actions">
                        <DownloadButton compact />
                        <RenewButton licenseId={license.id} />
                      </div>
                    </td>
                    <td>
                      <Link className="icon-button" href={`/licenses/${license.id}`} aria-label="Voir le detail">
                        <ChevronRight size={16} />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
