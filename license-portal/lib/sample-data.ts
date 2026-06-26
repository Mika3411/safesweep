import {
  PortalCustomer,
  PortalInvoice,
  PortalLicense,
  PortalPayment,
  PortalStripeWebhookEvent,
  PortalValidation
} from "@/lib/portal-types";

export const sampleInvoices: PortalInvoice[] = [
  {
    id: "inv_2026_0417",
    number: "INV-2026-0417",
    amountCents: 125000,
    currency: "eur",
    status: "paid",
    paidAt: "2026-05-15T00:00:00.000Z",
    createdAt: "2026-05-15T00:00:00.000Z"
  },
  {
    id: "inv_2025_0412",
    number: "INV-2025-0412",
    amountCents: 115000,
    currency: "eur",
    status: "paid",
    paidAt: "2025-05-15T00:00:00.000Z",
    createdAt: "2025-05-15T00:00:00.000Z"
  },
  {
    id: "inv_2024_0407",
    number: "INV-2024-0407",
    amountCents: 105000,
    currency: "eur",
    status: "paid",
    paidAt: "2024-05-15T00:00:00.000Z",
    createdAt: "2024-05-15T00:00:00.000Z"
  }
];

export const sampleLicenses: PortalLicense[] = [
  {
    id: "lic_endpoint",
    publicId: "SWP-ACME-0012",
    keyPrefix: "ACME",
    product: "ENDPOINT",
    status: "ACTIVE",
    expiresAt: "2026-08-15T00:00:00.000Z",
    deviceLimit: 10,
    seatCount: 10,
    devices: [
      {
        id: "dev_ws_01",
        name: "ACME-WS-01",
        platform: "Windows 11",
        activatedAt: "2026-05-12T09:00:00.000Z",
        lastSeenAt: "2026-06-20T10:00:00.000Z"
      },
      {
        id: "dev_ws_02",
        name: "ACME-WS-02",
        platform: "Windows 11",
        activatedAt: "2026-05-13T09:00:00.000Z",
        lastSeenAt: "2026-06-21T08:25:00.000Z"
      },
      {
        id: "dev_lap_07",
        name: "ACME-LAP-07",
        platform: "Windows 10",
        activatedAt: "2026-05-13T11:00:00.000Z",
        lastSeenAt: "2026-06-18T12:40:00.000Z"
      }
    ],
    invoices: sampleInvoices
  },
  {
    id: "lic_server",
    publicId: "SWP-ACME-0011",
    keyPrefix: "ACME",
    product: "SERVER",
    status: "ACTIVE",
    expiresAt: "2026-11-30T00:00:00.000Z",
    deviceLimit: 5,
    seatCount: 5,
    devices: [
      {
        id: "dev_srv_01",
        name: "ACME-SRV-01",
        platform: "Windows Server 2022",
        activatedAt: "2026-05-14T07:30:00.000Z",
        lastSeenAt: "2026-06-22T05:12:00.000Z"
      }
    ],
    invoices: []
  },
  {
    id: "lic_mobile",
    publicId: "SWP-ACME-0010",
    keyPrefix: "ACME",
    product: "MOBILE",
    status: "EXPIRED",
    expiresAt: "2025-05-10T00:00:00.000Z",
    deviceLimit: 3,
    seatCount: 3,
    devices: [],
    invoices: []
  },
  {
    id: "lic_suspended",
    publicId: "SWP-ACME-0009",
    keyPrefix: "ACME",
    product: "ENDPOINT",
    status: "SUSPENDED",
    expiresAt: "2026-09-20T00:00:00.000Z",
    deviceLimit: 5,
    seatCount: 5,
    devices: [],
    invoices: []
  },
  {
    id: "lic_revoked",
    publicId: "SWP-ACME-0008",
    keyPrefix: "ACME",
    product: "SERVER",
    status: "REVOKED",
    expiresAt: "2025-03-12T00:00:00.000Z",
    deviceLimit: 2,
    seatCount: 2,
    devices: [],
    invoices: []
  }
];

export const sampleCustomers: PortalCustomer[] = [
  {
    id: "cust_acme",
    name: "Camille Martin",
    company: "Acme Industries",
    email: "client@safesweep.test",
    licenseCount: 12,
    paymentCount: 3,
    status: "ACTIVE"
  },
  {
    id: "cust_globex",
    name: "Nora Vidal",
    company: "Globex Corporation",
    email: "it@globex.test",
    licenseCount: 8,
    paymentCount: 2,
    status: "ACTIVE"
  },
  {
    id: "cust_initech",
    name: "Samir Blanc",
    company: "Initech",
    email: "admin@initech.test",
    licenseCount: 5,
    paymentCount: 1,
    status: "ACTIVE"
  },
  {
    id: "cust_umbrella",
    name: "Lea Moreau",
    company: "Umbrella Corp.",
    email: "it@umbrella.test",
    licenseCount: 7,
    paymentCount: 4,
    status: "SUSPENDED"
  }
];

export const sampleValidations: PortalValidation[] = [
  {
    id: "val_1",
    createdAt: "2026-05-15T10:32:00.000Z",
    action: "Licence creee",
    result: "ALLOWED",
    reason: "admin@safesweep.test",
    licensePublicId: "SWP-ACME-0012"
  },
  {
    id: "val_2",
    createdAt: "2026-05-15T10:35:00.000Z",
    action: "Appareil active",
    result: "ALLOWED",
    reason: "system",
    licensePublicId: "SWP-ACME-0012",
    deviceName: "ACME-WS-01"
  },
  {
    id: "val_3",
    createdAt: "2026-05-20T09:12:00.000Z",
    action: "Expiration modifiee",
    result: "ALLOWED",
    reason: "15/08/2026 vers 15/11/2026",
    licensePublicId: "SWP-ACME-0012"
  },
  {
    id: "val_4",
    createdAt: "2026-05-22T14:47:00.000Z",
    action: "Suspension",
    result: "DENIED",
    reason: "Demande client",
    licensePublicId: "SWP-ACME-0009"
  }
];

export const samplePayments: PortalPayment[] = [
  {
    id: "pay_1",
    createdAt: "2026-05-15T00:00:00.000Z",
    client: "Acme Industries",
    invoice: "INV-2026-0417",
    amountCents: 125000,
    currency: "eur",
    status: "paid",
    method: "Carte"
  },
  {
    id: "pay_2",
    createdAt: "2026-05-15T00:00:00.000Z",
    client: "Globex Corporation",
    invoice: "INV-2026-0409",
    amountCents: 95000,
    currency: "eur",
    status: "paid",
    method: "Virement"
  },
  {
    id: "pay_3",
    createdAt: "2026-05-14T00:00:00.000Z",
    client: "Initech",
    invoice: "INV-2026-0403",
    amountCents: 60000,
    currency: "eur",
    status: "pending",
    method: "Virement"
  }
];

export const sampleStripeWebhookEvents: PortalStripeWebhookEvent[] = [
  {
    id: "stripe_webhook_evt_1",
    eventId: "evt_1QWebhook",
    type: "invoice.payment_succeeded",
    status: "PROCESSED",
    receivedCount: 1,
    lastReceivedAt: "2026-06-25T10:30:00.000Z",
    processedAt: "2026-06-25T10:30:01.000Z",
    error: null
  },
  {
    id: "stripe_webhook_evt_2",
    eventId: "evt_1QRetry",
    type: "checkout.session.completed",
    status: "FAILED",
    receivedCount: 2,
    lastReceivedAt: "2026-06-25T10:18:00.000Z",
    processedAt: null,
    error: "Stripe webhook processing failed."
  }
];
