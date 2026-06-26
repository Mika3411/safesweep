import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { encryptLicenseKey } from "@/lib/license-key-delivery";

const mocks = vi.hoisted(() => ({
  requireApiUser: vi.fn(),
  licenseFindFirst: vi.fn(),
  licenseUpdateMany: vi.fn(),
  auditLogCreate: vi.fn(),
  txAuditLogCreate: vi.fn(),
  transaction: vi.fn()
}));

vi.mock("@/lib/auth", () => ({
  requireApiUser: mocks.requireApiUser
}));

vi.mock("@/lib/db", () => ({
  prisma: {
    license: {
      findFirst: mocks.licenseFindFirst
    },
    auditLog: {
      create: mocks.auditLogCreate
    },
    $transaction: mocks.transaction
  }
}));

import { POST } from "@/app/api/customer/licenses/[id]/reveal/route";

const originalAppUrl = process.env.APP_URL;
const originalEncryptionSecret = process.env.LICENSE_KEY_ENCRYPTION_SECRET;

function restoreEnv(name: string, value: string | undefined) {
  if (value === undefined) {
    delete process.env[name];
  } else {
    process.env[name] = value;
  }
}

function request() {
  return new NextRequest("https://portal.example/api/customer/licenses/license-id/reveal", {
    method: "POST",
    headers: {
      host: "portal.example",
      origin: "https://portal.example"
    }
  });
}

describe("one-time license key reveal route", () => {
  beforeEach(() => {
    process.env.APP_URL = "https://portal.example";
    process.env.LICENSE_KEY_ENCRYPTION_SECRET = "test-license-key-encryption-secret-32";
    vi.clearAllMocks();
    mocks.requireApiUser.mockResolvedValue({ id: "user-id", email: "client@example.com", role: "CUSTOMER" });
    mocks.licenseUpdateMany.mockResolvedValue({ count: 1 });
    mocks.transaction.mockImplementation(async (callback) =>
      callback({
        license: { updateMany: mocks.licenseUpdateMany },
        auditLog: { create: mocks.txAuditLogCreate }
      })
    );
  });

  afterEach(() => {
    restoreEnv("APP_URL", originalAppUrl);
    restoreEnv("LICENSE_KEY_ENCRYPTION_SECRET", originalEncryptionSecret);
  });

  it("reveals the key once and clears the encrypted copy", async () => {
    mocks.licenseFindFirst.mockResolvedValue({
      id: "license-id",
      publicId: "SWP-ACME-0001",
      keyPrefix: "ABCD",
      encryptedLicenseKey: encryptLicenseKey("ABCD-EFGH-2345-MNPQ"),
      licenseKeyRevealedAt: null
    });

    const response = await POST(request(), { params: Promise.resolve({ id: "license-id" }) });
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body).toMatchObject({ licenseKey: "ABCD-EFGH-2345-MNPQ" });
    expect(mocks.licenseUpdateMany).toHaveBeenCalledWith({
      where: {
        id: "license-id",
        encryptedLicenseKey: { not: null },
        licenseKeyRevealedAt: null
      },
      data: {
        encryptedLicenseKey: null,
        licenseKeyRevealedAt: expect.any(Date)
      }
    });
    expect(mocks.txAuditLogCreate).toHaveBeenCalledWith({
      data: expect.objectContaining({
        action: "LICENSE_KEY_REVEALED",
        target: "SWP-ACME-0001"
      })
    });
  });

  it("blocks a second reveal and logs the denied attempt", async () => {
    mocks.licenseFindFirst.mockResolvedValue({
      id: "license-id",
      publicId: "SWP-ACME-0001",
      keyPrefix: "ABCD",
      encryptedLicenseKey: null,
      licenseKeyRevealedAt: new Date("2026-06-25T12:00:00.000Z")
    });

    const response = await POST(request(), { params: Promise.resolve({ id: "license-id" }) });

    expect(response.status).toBe(409);
    await expect(response.json()).resolves.toMatchObject({ error: "Cle de licence deja revelee ou indisponible." });
    expect(mocks.transaction).not.toHaveBeenCalled();
    expect(mocks.auditLogCreate).toHaveBeenCalledWith({
      data: expect.objectContaining({
        action: "LICENSE_KEY_REVEAL_DENIED",
        metadata: expect.objectContaining({ reason: "already_revealed" })
      })
    });
  });
});
