import { requireUser } from "@/lib/auth";
import { AppShell } from "@/components/AppShell";
import { CustomerLicenseDetailView } from "@/components/customer/CustomerLicenseDetailView";

export default async function LicenseDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const [user, resolvedParams] = await Promise.all([requireUser(), params]);

  return (
    <AppShell mode="client" title="Detail d'une licence" userName={user.company ?? user.name} userRole="Client">
      <CustomerLicenseDetailView licenseId={resolvedParams.id} />
    </AppShell>
  );
}
