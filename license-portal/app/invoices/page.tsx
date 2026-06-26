import { requireUser } from "@/lib/auth";
import { AppShell } from "@/components/AppShell";
import { CustomerInvoicesView } from "@/components/customer/CustomerInvoicesView";

export default async function InvoicesPage() {
  const user = await requireUser();

  return (
    <AppShell mode="client" title="Factures" userName={user.company ?? user.name} userRole="Client">
      <CustomerInvoicesView />
    </AppShell>
  );
}
