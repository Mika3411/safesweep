import { NextRequest } from "next/server";
import { afterEach, describe, expect, it } from "vitest";
import {
  checkSoftwareClientSecret,
  getRemainingActivations,
  licenseDeviceRequestSchema,
  sanitizeLicenseForApi
} from "@/lib/license-api";

const originalLicenseApiSecret = process.env.LICENSE_API_SECRET;

function secretRequest(secret?: string) {
  return new NextRequest("http://localhost/api/license/validate", {
    headers: secret ? { "x-safesweep-client-secret": secret } : undefined
  });
}

describe("license API contract", () => {
  afterEach(() => {
    if (originalLicenseApiSecret === undefined) {
      delete process.env.LICENSE_API_SECRET;
    } else {
      process.env.LICENSE_API_SECRET = originalLicenseApiSecret;
    }
  });

  it("accepts the software client payload shape", () => {
    const payload = licenseDeviceRequestSchema.parse({
      licenseKey: "ABCD-EFGH-IJKL-MNOP",
      deviceId: "PC-123456",
      deviceName: "Ordinateur de Jean"
    });

    expect(payload.deviceId).toBe("PC-123456");
    expect(payload.deviceName).toBe("Ordinateur de Jean");
  });

  it("rejects incomplete activation payloads", () => {
    const result = licenseDeviceRequestSchema.safeParse({
      licenseKey: "ABCD-EFGH-IJKL-MNOP",
      deviceId: "PC"
    });

    expect(result.success).toBe(false);
  });

  it("rejects unexpected public desktop payload fields", () => {
    const result = licenseDeviceRequestSchema.safeParse({
      licenseKey: "ABCD-EFGH-IJKL-MNOP",
      deviceId: "PC-123456",
      deviceName: "Ordinateur de Jean",
      serverSecret: "do-not-send-this"
    });

    expect(result.success).toBe(false);
  });

  it("never returns negative remaining activations", () => {
    expect(getRemainingActivations(3, 1)).toBe(2);
    expect(getRemainingActivations(3, 3)).toBe(0);
    expect(getRemainingActivations(3, 9)).toBe(0);
  });

  it("does not trust a software client secret when the server secret is absent", () => {
    process.env.LICENSE_API_SECRET = "";

    expect(checkSoftwareClientSecret(secretRequest("client-secret"))).toBe(false);
  });

  it("accepts only the matching optional server-to-server software client secret", () => {
    process.env.LICENSE_API_SECRET = "client-secret";

    expect(checkSoftwareClientSecret(secretRequest("client-secret"))).toBe(true);
    expect(checkSoftwareClientSecret(secretRequest("wrong-secret"))).toBe(false);
    expect(checkSoftwareClientSecret(secretRequest())).toBe(false);
  });

  it("strips sensitive Prisma fields from public license payloads", () => {
    const now = new Date("2026-06-25T12:00:00.000Z");
    const rawLicense = {
      id: "license-id",
      publicId: "ACME-ENDPOINT-001",
      keyHash: "stored-key-hash",
      keyPrefix: "ACME",
      encryptedLicenseKey: "encrypted-key-envelope",
      licenseKeyRevealedAt: null,
      ownerId: "owner-id",
      product: "ENDPOINT",
      status: "ACTIVE",
      expiresAt: now,
      deviceLimit: 3,
      seatCount: 3,
      subscriptionId: null,
      devices: [
        {
          id: "device-id",
          licenseId: "license-id",
          fingerprintHash: "stored-fingerprint-hash",
          name: "Workstation",
          platform: "Windows",
          activatedAt: now,
          deactivatedAt: null,
          lastSeenAt: now
        }
      ],
      invoices: [
        {
          id: "invoice-id",
          userId: "owner-id",
          licenseId: "license-id",
          stripeInvoiceId: "stripe-invoice-id",
          number: "INV-001",
          amountCents: 9900,
          currency: "eur",
          status: "paid",
          hostedInvoiceUrl: "https://billing.example/invoice",
          invoicePdfUrl: "https://billing.example/invoice.pdf",
          paidAt: now,
          dueAt: null,
          createdAt: now
        }
      ],
      validations: [
        {
          id: "validation-id",
          fingerprintHash: "stored-fingerprint-hash",
          ipHash: "stored-ip-hash"
        }
      ],
      createdAt: now,
      updatedAt: now
    } as unknown as Parameters<typeof sanitizeLicenseForApi>[0] & Record<string, unknown>;

    const payload = sanitizeLicenseForApi(rawLicense);

    expect(payload).not.toHaveProperty("keyHash");
    expect(payload).not.toHaveProperty("encryptedLicenseKey");
    expect(payload).not.toHaveProperty("ownerId");
    expect(payload).not.toHaveProperty("validations");
    expect(payload.devices[0]).not.toHaveProperty("fingerprintHash");
    expect(payload.devices[0]).not.toHaveProperty("licenseId");
    expect(payload.invoices[0]).not.toHaveProperty("stripeInvoiceId");
    expect(payload.invoices[0]).not.toHaveProperty("userId");
    expect(payload.invoices[0]).not.toHaveProperty("licenseId");
    expect(payload.licenseKeyAvailable).toBe(true);
  });
});
