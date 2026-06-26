import { requireUser } from "@/lib/auth";
import { AppShell } from "@/components/AppShell";
import { CustomerAccountView } from "@/components/customer/CustomerAccountView";

export default async function AccountPage() {
  const user = await requireUser();

  return (
    <AppShell mode="client" title="Parametres du compte" userName={user.company ?? user.name} userRole="Client">
      <CustomerAccountView />
    </AppShell>
  );
}
