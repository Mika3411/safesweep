import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  requireApiUser: vi.fn(),
  licenseValidationFindMany: vi.fn(),
  deviceFindMany: vi.fn(),
  licenseUpdate: vi.fn(),
  auditLogCreate: vi.fn()
}));

vi.mock("@/lib/auth", () => ({
  requireApiUser: mocks.requireApiUser
}));

vi.mock("@/lib/db", () => ({
  prisma: {
    licenseValidation: {
      findMany: mocks.licenseValidationFindMany
    },
    device: {
      findMany: mocks.deviceFindMany
    },
    license: {
      update: mocks.licenseUpdate
    },
    auditLog: {
      create: mocks.auditLogCreate
    }
  }
}));

import { GET as listAdminValidations } from "@/app/api/admin/validations/route";
import { GET as listAdminLicenseDevices } from "@/app/api/admin/licenses/[id]/devices/route";
import { PATCH as updateAdminLicenseStatus } from "@/app/api/admin/licenses/[id]/status/route";
import { PATCH as updateAdminLicenseExpiration } from "@/app/api/admin/licenses/[id]/expiration/route";

const sensitiveKeys = ["keyHash", "encryptedLicenseKey", "fingerprintHash", "ipHash", "ownerId", "licenseId", "deviceId"];

function collectKeys(value: unknown, keys: string[] = []) {
  if (Array.isArray(value)) {
    value.forEach((item) => collectKeys(item, keys));
    return keys;
  }

  if (value && typeof value === "object") {
    for (const [key, child] of Object.entries(value)) {
      keys.push(key);
      collectKeys(child, keys);
    }
  }

  return keys;
}

function expectNoSensitiveKeys(payload: unknown) {
  const keys = collectKeys(payload);

  for (const sensitiveKey of sensitiveKeys) {
    expect(keys).not.toContain(sensitiveKey);
  }
}

function adminRequest(body: Record<string, unknown>) {
  return new NextRequest("https://portal.example/api/admin/licenses/license-id/status", {
    method: "PATCH",
    headers: {
      host: "portal.example",
      origin: "https://portal.example",
      "content-type": "application/json"
    },
    body: JSON.stringify(body)
  });
}

function rawLicense() {
  const now = new Date("2026-06-25T12:00:00.000Z");

  return {
    id: "license-id",
    publicId: "SWP-ACME-0001",
    keyHash: "stored-key-hash",
    keyPrefix: "ABCD",
    encryptedLicenseKey: "encrypted",
    licenseKeyRevealedAt: null,
    ownerId: "owner-id",
    product: "ENDPOINT",
    status: "ACTIVE",
    expiresAt: now,
    deviceLimit: 3,
    seatCount: 3,
    subscriptionId: "sub_123",
    devices: [
      {
        id: "device-id",
        licenseId: "license-id",
        fingerprintHash: "fingerprint-hash",
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
        stripeInvoiceId: "in_123",
        number: "INV-001",
        amountCents: 9900,
        currency: "eur",
        status: "paid",
        paidAt: now,
        dueAt: null,
        createdAt: now,
        hostedInvoiceUrl: null,
        invoicePdfUrl: null
      }
    ],
    owner: {
      id: "owner-id",
      name: "Client",
      email: "client@example.com",
      company: "Acme"
    },
    createdAt: now,
    updatedAt: now
  };
}

describe("public API responses do not expose sensitive Prisma fields", () => {
  beforeEach(() => {
    process.env.APP_URL = "https://portal.example";
    vi.clearAllMocks();
    mocks.requireApiUser.mockResolvedValue({ id: "admin-id", role: "ADMIN", email: "admin@example.com" });
    mocks.auditLogCreate.mockResolvedValue({});
  });

  it("sanitizes admin validation logs", async () => {
    mocks.licenseValidationFindMany.mockResolvedValue([
      {
        id: "validation-id",
        licenseId: "license-id",
        deviceId: "device-id",
        fingerprintHash: "fingerprint-hash",
        ipHash: "ip-hash",
        action: "VALIDATED",
        result: "ALLOWED",
        reason: "OK",
        createdAt: new Date("2026-06-25T12:00:00.000Z"),
        license: { publicId: "SWP-ACME-0001", product: "ENDPOINT" },
        device: { name: "Workstation", platform: "Windows" }
      }
    ]);

    const response = await listAdminValidations();
    const body = await response.json();

    expect(response.status).toBe(200);
    expectNoSensitiveKeys(body);
    expect(body.validations[0]).toMatchObject({
      id: "validation-id",
      licensePublicId: "SWP-ACME-0001",
      deviceName: "Workstation"
    });
  });

  it("sanitizes admin license device listings", async () => {
    mocks.deviceFindMany.mockResolvedValue([
      {
        id: "device-id",
        licenseId: "license-id",
        fingerprintHash: "fingerprint-hash",
        name: "Workstation",
        platform: "Windows",
        activatedAt: new Date("2026-06-25T12:00:00.000Z"),
        deactivatedAt: null,
        lastSeenAt: new Date("2026-06-25T12:00:00.000Z")
      }
    ]);

    const response = await listAdminLicenseDevices(new Request("https://portal.example") as Request, {
      params: Promise.resolve({ id: "license-id" })
    });
    const body = await response.json();

    expect(response.status).toBe(200);
    expectNoSensitiveKeys(body);
    expect(body.devices[0]).toMatchObject({
      id: "device-id",
      name: "Workstation",
      platform: "Windows"
    });
  });

  it("sanitizes admin license status updates", async () => {
    mocks.licenseUpdate.mockResolvedValue(rawLicense());

    const response = await updateAdminLicenseStatus(adminRequest({ status: "SUSPENDED" }), {
      params: Promise.resolve({ id: "license-id" })
    });
    const body = await response.json();

    expect(response.status).toBe(200);
    expectNoSensitiveKeys(body);
    expect(body.license).toMatchObject({
      publicId: "SWP-ACME-0001",
      status: "active"
    });
  });

  it("sanitizes admin license expiration updates", async () => {
    mocks.licenseUpdate.mockResolvedValue(rawLicense());

    const response = await updateAdminLicenseExpiration(adminRequest({ expiresAt: "2027-06-25T00:00:00.000Z" }), {
      params: Promise.resolve({ id: "license-id" })
    });
    const body = await response.json();

    expect(response.status).toBe(200);
    expectNoSensitiveKeys(body);
    expect(body.license).toMatchObject({
      publicId: "SWP-ACME-0001",
      maxActivations: 3
    });
  });
});
