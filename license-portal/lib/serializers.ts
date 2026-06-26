import {
  PortalCustomer,
  PortalDevice,
  PortalInvoice,
  PortalLicense,
  PortalPayment,
  PortalStripeWebhookEvent,
  PortalValidation
} from "@/lib/portal-types";

type RawDate = Date | string | null | undefined;

type RawDevice = {
  id: string;
  name: string;
  platform?: string | null;
  activatedAt: RawDate;
  deactivatedAt?: RawDate;
  lastSeenAt?: RawDate;
};

type RawInvoice = {
  id: string;
  number: string;
  amountCents: number;
  currency: string;
  status: string;
  paidAt?: RawDate;
  dueAt?: RawDate;
  createdAt: RawDate;
  hostedInvoiceUrl?: string | null;
  invoicePdfUrl?: string | null;
};

type RawLicense = {
  id: string;
  publicId: string;
  keyPrefix: string;
  encryptedLicenseKey?: string | null;
  licenseKeyRevealedAt?: RawDate;
  product: string;
  status: string;
  expiresAt: RawDate;
  deviceLimit: number;
  seatCount: number;
  subscriptionId?: string | null;
  devices?: RawDevice[];
  invoices?: RawInvoice[];
  owner?: {
    id: string;
    name: string;
    email: string;
    company?: string | null;
  } | null;
};

function iso(value: RawDate) {
  return value ? new Date(value).toISOString() : "";
}

export function serializeDevice(device: RawDevice): PortalDevice {
  return {
    id: device.id,
    name: device.name,
    platform: device.platform,
    activatedAt: iso(device.activatedAt),
    deactivatedAt: device.deactivatedAt ? iso(device.deactivatedAt) : null,
    lastSeenAt: device.lastSeenAt ? iso(device.lastSeenAt) : null
  };
}

export function serializeInvoice(invoice: RawInvoice): PortalInvoice {
  return {
    id: invoice.id,
    number: invoice.number,
    amountCents: invoice.amountCents,
    currency: invoice.currency,
    status: invoice.status,
    paidAt: invoice.paidAt ? iso(invoice.paidAt) : null,
    dueAt: invoice.dueAt ? iso(invoice.dueAt) : null,
    createdAt: iso(invoice.createdAt),
    hostedInvoiceUrl: invoice.hostedInvoiceUrl,
    invoicePdfUrl: invoice.invoicePdfUrl
  };
}

export function serializeLicense(license: RawLicense): PortalLicense {
  return {
    id: license.id,
    publicId: license.publicId,
    keyPrefix: license.keyPrefix,
    licenseKeyAvailable: Boolean(license.encryptedLicenseKey && !license.licenseKeyRevealedAt),
    licenseKeyRevealedAt: license.licenseKeyRevealedAt ? iso(license.licenseKeyRevealedAt) : null,
    product: license.product,
    status: license.status,
    expiresAt: iso(license.expiresAt),
    deviceLimit: license.deviceLimit,
    seatCount: license.seatCount,
    subscriptionId: license.subscriptionId,
    devices: (license.devices ?? []).map(serializeDevice),
    invoices: (license.invoices ?? []).map(serializeInvoice),
    owner: license.owner ?? undefined
  };
}

export function serializeCustomer(customer: {
  id: string;
  name: string;
  company?: string | null;
  email: string;
  _count?: { licenses?: number; payments?: number };
}): PortalCustomer {
  return {
    id: customer.id,
    name: customer.name,
    company: customer.company,
    email: customer.email,
    licenseCount: customer._count?.licenses ?? 0,
    paymentCount: customer._count?.payments ?? 0,
    status: "ACTIVE"
  };
}

export function serializeValidation(validation: {
  id: string;
  createdAt: RawDate;
  action: string;
  result: string;
  reason?: string | null;
  license?: { publicId: string } | null;
  device?: { name: string } | null;
}): PortalValidation {
  return {
    id: validation.id,
    createdAt: iso(validation.createdAt),
    action: validation.action,
    result: validation.result,
    reason: validation.reason,
    licensePublicId: validation.license?.publicId,
    deviceName: validation.device?.name
  };
}

export function serializePayment(payment: {
  id: string;
  createdAt: RawDate;
  amountCents: number;
  currency: string;
  status: string;
  method?: string | null;
  user?: { name: string; company?: string | null } | null;
}): PortalPayment {
  return {
    id: payment.id,
    createdAt: iso(payment.createdAt),
    client: payment.user?.company ?? payment.user?.name ?? "Client inconnu",
    invoice: null,
    amountCents: payment.amountCents,
    currency: payment.currency,
    status: payment.status,
    method: payment.method
  };
}

export function serializeStripeWebhookEvent(event: {
  id: string;
  eventId: string;
  type: string;
  status: string;
  error?: string | null;
  receivedCount: number;
  lastReceivedAt: RawDate;
  processedAt?: RawDate;
}): PortalStripeWebhookEvent {
  return {
    id: event.id,
    eventId: event.eventId,
    type: event.type,
    status: event.status,
    error: event.error,
    receivedCount: event.receivedCount,
    lastReceivedAt: iso(event.lastReceivedAt),
    processedAt: event.processedAt ? iso(event.processedAt) : null
  };
}
