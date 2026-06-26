"use client";

import { Download, ReceiptText } from "lucide-react";
import { useEffect, useState } from "react";
import { getCustomerInvoices } from "@/lib/customer-api";
import { formatCurrency, formatDate } from "@/lib/format";
import { PortalInvoice } from "@/lib/portal-types";
import { EmptyState, ErrorState, LoadingState } from "@/components/customer/CustomerStates";
import { StatusBadge } from "@/components/StatusBadge";

export function CustomerInvoicesView() {
  const [invoices, setInvoices] = useState<PortalInvoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);

    try {
      setInvoices(await getCustomerInvoices());
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Chargement impossible.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  if (loading) {
    return <LoadingState label="Chargement des factures..." />;
  }

  if (error) {
    return <ErrorState message={error} onRetry={load} />;
  }

  return (
    <main className="customer-page">
      <section className="main-panel">
        <div className="panel-heading">
          <h2>Factures</h2>
        </div>

        {invoices.length === 0 ? (
          <EmptyState title="Aucune facture" description="Votre historique de facturation apparaitra ici." />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Facture</th>
                  <th>Date</th>
                  <th>Montant</th>
                  <th>Statut</th>
                  <th>PDF</th>
                </tr>
              </thead>
              <tbody>
                {invoices.map((invoice) => (
                  <tr key={invoice.id}>
                    <td>
                      <ReceiptText size={15} /> {invoice.number}
                    </td>
                    <td>{formatDate(invoice.paidAt ?? invoice.createdAt)}</td>
                    <td>{formatCurrency(invoice.amountCents, invoice.currency)}</td>
                    <td>
                      <StatusBadge status={invoice.status} />
                    </td>
                    <td>
                      <a className="secondary-button" href={invoice.invoicePdfUrl ?? "#"}>
                        <Download size={15} />
                        PDF
                      </a>
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
