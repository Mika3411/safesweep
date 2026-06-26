import { requireUser } from "@/lib/auth";
import { AppShell } from "@/components/AppShell";
import { CustomerDevicesView } from "@/components/customer/CustomerDevicesView";

export default async function DevicesPage() {
  const user = await requireUser();

  return (
    <AppShell mode="client" title="Mes appareils actives" userName={user.company ?? user.name} userRole="Client">
      <CustomerDevicesView />
    </AppShell>
  );
}
