import {
  sampleCustomers,
  sampleInvoices,
  sampleLicenses,
  samplePayments,
  sampleStripeWebhookEvents,
  sampleValidations
} from "@/lib/sample-data";
import { AdminPortal } from "@/components/AdminPortal";
import { ClientPortal } from "@/components/ClientPortal";

export default function DemoPage() {
  const adminLicenses = sampleLicenses.map((license) => ({
    ...license,
    owner: {
      id: "cust_acme",
      name: "Camille Martin",
      email: "client@safesweep.test",
      company: "Acme Industries"
    }
  }));

  return (
    <div className="demo-stack">
      <ClientPortal
        demo
        userName="Camille Martin"
        company="Acme Industries"
        licenses={sampleLicenses}
        invoices={sampleInvoices}
      />
      <AdminPortal
        demo
        userName="Admin SafeSweep"
        customers={sampleCustomers}
        licenses={adminLicenses}
        validations={sampleValidations}
        payments={samplePayments}
        stripeWebhookEvents={sampleStripeWebhookEvents}
      />
    </div>
  );
}
