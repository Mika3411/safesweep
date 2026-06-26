export type PortalDevice = {
  id: string;
  name: string;
  platform?: string | null;
  activatedAt: string;
  deactivatedAt?: string | null;
  lastSeenAt?: string | null;
};

export type PortalInvoice = {
  id: string;
  number: string;
  amountCents: number;
  currency: string;
  status: string;
  paidAt?: string | null;
  dueAt?: string | null;
  createdAt: string;
  hostedInvoiceUrl?: string | null;
  invoicePdfUrl?: string | null;
};

export type PortalLicense = {
  id: string;
  publicId: string;
  keyPrefix: string;
  licenseKeyAvailable?: boolean;
  licenseKeyRevealedAt?: string | null;
  product: "ENDPOINT" | "SERVER" | "MOBILE" | string;
  status: "ACTIVE" | "EXPIRED" | "SUSPENDED" | "REVOKED" | string;
  expiresAt: string;
  deviceLimit: number;
  seatCount: number;
  subscriptionId?: string | null;
  devices: PortalDevice[];
  invoices: PortalInvoice[];
  owner?: {
    id: string;
    name: string;
    email: string;
    company?: string | null;
  };
};

export type PortalCustomer = {
  id: string;
  name: string;
  company?: string | null;
  email: string;
  licenseCount: number;
  paymentCount: number;
  status: "ACTIVE" | "SUSPENDED";
};

export type PortalValidation = {
  id: string;
  createdAt: string;
  action: string;
  result: string;
  reason?: string | null;
  licensePublicId?: string | null;
  deviceName?: string | null;
};

export type PortalPayment = {
  id: string;
  createdAt: string;
  client: string;
  invoice?: string | null;
  amountCents: number;
  currency: string;
  status: string;
  method?: string | null;
};

export type PortalStripeWebhookEvent = {
  id: string;
  eventId: string;
  type: string;
  status: "PROCESSING" | "PROCESSED" | "FAILED" | string;
  error?: string | null;
  receivedCount: number;
  lastReceivedAt: string;
  processedAt?: string | null;
};
