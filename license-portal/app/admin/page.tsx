import { requireAdmin } from "@/lib/auth";
import { prisma } from "@/lib/db";
import {
  serializeCustomer,
  serializeLicense,
  serializePayment,
  serializeStripeWebhookEvent,
  serializeValidation
} from "@/lib/serializers";
import { AdminPortal } from "@/components/AdminPortal";

export default async function AdminPage() {
  const user = await requireAdmin();
  const [customers, licenses, validations, payments, stripeWebhookEvents] = await Promise.all([
    prisma.user.findMany({
      where: { role: "CUSTOMER" },
      select: {
        id: true,
        name: true,
        company: true,
        email: true,
        _count: { select: { licenses: true, payments: true } }
      },
      orderBy: { createdAt: "desc" }
    }),
    prisma.license.findMany({
      include: {
        owner: { select: { id: true, name: true, email: true, company: true } },
        devices: { orderBy: { activatedAt: "desc" } },
        invoices: { orderBy: { createdAt: "desc" }, take: 3 }
      },
      orderBy: { createdAt: "desc" },
      take: 100
    }),
    prisma.licenseValidation.findMany({
      include: {
        license: { select: { publicId: true } },
        device: { select: { name: true } }
      },
      orderBy: { createdAt: "desc" },
      take: 100
    }),
    prisma.payment.findMany({
      include: {
        user: { select: { name: true, company: true } }
      },
      orderBy: { createdAt: "desc" },
      take: 100
    }),
    prisma.stripeWebhookEvent.findMany({
      orderBy: { lastReceivedAt: "desc" },
      take: 50
    })
  ]);

  return (
    <AdminPortal
      userName={user.name}
      customers={customers.map(serializeCustomer)}
      licenses={licenses.map(serializeLicense)}
      validations={validations.map(serializeValidation)}
      payments={payments.map(serializePayment)}
      stripeWebhookEvents={stripeWebhookEvents.map(serializeStripeWebhookEvent)}
    />
  );
}
