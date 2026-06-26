import { requireUser } from "@/lib/auth";
import { AppShell } from "@/components/AppShell";
import { CustomerDashboardView } from "@/components/customer/CustomerDashboardView";

export default async function DashboardPage() {
  const user = await requireUser();

  return (
    <AppShell mode="client" title="Tableau de bord" userName={user.company ?? user.name} userRole="Client">
      <CustomerDashboardView />
    </AppShell>
  );
}
