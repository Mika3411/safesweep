import { requireUser } from "@/lib/auth";
import { AppShell } from "@/components/AppShell";
import { CustomerDownloadView } from "@/components/customer/CustomerDownloadView";

export default async function DownloadPage() {
  const user = await requireUser();

  return (
    <AppShell mode="client" title="Telecharger le logiciel" userName={user.company ?? user.name} userRole="Client">
      <CustomerDownloadView />
    </AppShell>
  );
}
