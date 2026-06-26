import { requireUser } from "@/lib/auth";
import { AppShell } from "@/components/AppShell";
import { CustomerLicensesView } from "@/components/customer/CustomerLicensesView";

export default async function LicensesPage() {
  const user = await requireUser();

  return (
    <AppShell mode="client" title="Mes licences" userName={user.company ?? user.name} userRole="Client">
      <CustomerLicensesView />
    </AppShell>
  );
}
