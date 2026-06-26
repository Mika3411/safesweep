import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { hashFingerprint } from "@/lib/license";
import { resetRateLimitForTests } from "@/lib/rate-limit";

const TEST_CLIENT_SECRET = "test-client-secret";
const TEST_REDIS_URL = "https://redis.example";
const TEST_REDIS_TOKEN = "redis-token";
const originalLicenseApiSecret = process.env.LICENSE_API_SECRET;
const originalRedisUrl = process.env.UPSTASH_REDIS_REST_URL;
const originalRedisToken = process.env.UPSTASH_REDIS_REST_TOKEN;

function restoreEnv(name: string, value: string | undefined) {
  if (value === undefined) {
    delete process.env[name];
  } else {
    process.env[name] = value;
  }
}

const db = vi.hoisted(() => {
  const licenseFindUnique = vi.fn();
  const licenseUpdate = vi.fn();
  const licenseValidationCreate = vi.fn();
  const deviceCreate = vi.fn();
  const deviceUpdate = vi.fn();
  const transaction = vi.fn();

  return {
    licenseFindUnique,
    licenseUpdate,
    licenseValidationCreate,
    deviceCreate,
    deviceUpdate,
    transaction,
    tx: {
      license: {
        findUnique: licenseFindUnique,
        update: licenseUpdate
      },
      licenseValidation: {
        create: licenseValidationCreate
      },
      device: {
        create: deviceCreate,
        update: deviceUpdate
      }
    }
  };
});

vi.mock("@/lib/db", () => ({
  prisma: {
    $transaction: db.transaction,
    licenseValidation: {
      create: db.licenseValidationCreate
    }
  }
}));

import { POST as disabledLegacyValidate } from "@/app/api/licenses/validate/route";
import { POST as activateLicense } from "@/app/api/license/activate/route";
import { POST as deactivateLicense } from "@/app/api/license/deactivate/route";
import { POST as validateLicense } from "@/app/api/license/validate/route";

function request(body: Record<string, unknown>, path = "/api/license/validate", includeSecret = true) {
  const headers: Record<string, string> = {
    "content-type": "application/json",
    "x-forwarded-for": "127.0.0.1"
  };

  if (includeSecret) {
    headers["x-safesweep-client-secret"] = TEST_CLIENT_SECRET;
  }

  return new NextRequest(`http://localhost${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body)
  });
}

function activeLicense(devices: unknown[]) {
  return {
    id: "license-id",
    publicId: "SWP-ACME-0001",
    product: "ENDPOINT",
    status: "ACTIVE",
    expiresAt: new Date("2027-06-25T00:00:00.000Z"),
    deviceLimit: 3,
    devices
  };
}

describe("legacy /api/licenses/validate", () => {
  beforeEach(() => {
    process.env.LICENSE_API_SECRET = TEST_CLIENT_SECRET;
    process.env.UPSTASH_REDIS_REST_URL = TEST_REDIS_URL;
    process.env.UPSTASH_REDIS_REST_TOKEN = TEST_REDIS_TOKEN;
    resetRateLimitForTests();
    vi.clearAllMocks();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        Response.json({
          result: [1, 60_000]
        })
      )
    );
    db.transaction.mockImplementation(async (callback) => callback(db.tx));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    restoreEnv("LICENSE_API_SECRET", originalLicenseApiSecret);
    restoreEnv("UPSTASH_REDIS_REST_URL", originalRedisUrl);
    restoreEnv("UPSTASH_REDIS_REST_TOKEN", originalRedisToken);
  });

  it("is disabled without touching persistence", async () => {
    const response = await disabledLegacyValidate();

    expect(response.status).toBe(410);
    await expect(response.json()).resolves.toMatchObject({
      error: "Endpoint de validation obsolete desactive. Utilisez /api/license/validate."
    });
    expect(db.transaction).not.toHaveBeenCalled();
    expect(db.licenseValidationCreate).not.toHaveBeenCalled();
  });

  it("does not create a device during current validation", async () => {
    db.licenseFindUnique.mockResolvedValue(activeLicense([]));

    const response = await validateLicense(
      request({
        licenseKey: "ABCD-EFGH-IJKL-MNOP",
        deviceId: "NEW-DEVICE-001",
        deviceName: "New workstation",
        platform: "Windows"
      })
    );
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body).toMatchObject({
      valid: true,
      remainingActivations: 3,
      deviceAuthorized: false,
      requiresActivation: true
    });
    expect(db.deviceCreate).not.toHaveBeenCalled();
    expect(db.deviceUpdate).not.toHaveBeenCalled();
    expect(db.licenseValidationCreate).toHaveBeenCalledWith({
      data: expect.objectContaining({
        action: "VALIDATED",
        result: "ALLOWED",
        reason: "Activation disponible"
      })
    });
  });

  it("accepts desktop validation without the software client secret header", async () => {
    db.licenseFindUnique.mockResolvedValue(activeLicense([]));

    const response = await validateLicense(
      request(
        {
          licenseKey: "ABCD-EFGH-IJKL-MNOP",
          deviceId: "SAFE-SWEEP-DESKTOP-001",
          deviceName: "Desktop client",
          platform: "Windows"
        },
        "/api/license/validate",
        false
      )
    );
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body).toMatchObject({
      valid: true,
      deviceAuthorized: false,
      requiresActivation: true
    });
    expect(db.licenseValidationCreate).toHaveBeenCalledWith({
      data: expect.objectContaining({
        action: "VALIDATED",
        result: "ALLOWED",
        ipHash: expect.any(String),
        fingerprintHash: expect.any(String)
      })
    });
  });

  it("accepts desktop activation without the software client secret header", async () => {
    db.licenseFindUnique.mockResolvedValue(activeLicense([]));
    db.deviceCreate.mockResolvedValue({ id: "new-device-id" });

    const response = await activateLicense(
      request(
        {
          licenseKey: "ABCD-EFGH-IJKL-MNOP",
          deviceId: "SAFE-SWEEP-DESKTOP-002",
          deviceName: "Desktop client",
          platform: "Windows"
        },
        "/api/license/activate",
        false
      )
    );
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body).toMatchObject({
      valid: true,
      activated: true,
      remainingActivations: 2
    });
    expect(db.deviceCreate).toHaveBeenCalledWith({
      data: expect.objectContaining({
        fingerprintHash: hashFingerprint("SAFE-SWEEP-DESKTOP-002"),
        name: "Desktop client",
        platform: "Windows"
      })
    });
  });

  it("accepts desktop deactivation without the software client secret header", async () => {
    const deviceId = "SAFE-SWEEP-DESKTOP-003";
    db.licenseFindUnique.mockResolvedValue(
      activeLicense([
        {
          id: "device-id",
          fingerprintHash: hashFingerprint(deviceId),
          deactivatedAt: null
        }
      ])
    );
    db.deviceUpdate.mockResolvedValue({});

    const response = await deactivateLicense(
      request(
        {
          licenseKey: "ABCD-EFGH-IJKL-MNOP",
          deviceId,
          deviceName: "Desktop client",
          platform: "Windows"
        },
        "/api/license/deactivate",
        false
      )
    );
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body).toMatchObject({
      valid: true,
      deactivated: true,
      remainingActivations: 3
    });
    expect(db.deviceUpdate).toHaveBeenCalledWith({
      where: { id: "device-id" },
      data: expect.objectContaining({
        deactivatedAt: expect.any(Date),
        lastSeenAt: expect.any(Date)
      })
    });
  });

  it("does not reactivate a deactivated device during current validation", async () => {
    const deviceFingerprint = "KNOWN-DEACTIVATED-001";

    db.licenseFindUnique.mockResolvedValue(
      activeLicense([
        {
          id: "device-id",
          fingerprintHash: hashFingerprint(deviceFingerprint),
          deactivatedAt: new Date("2026-01-01T00:00:00.000Z")
        }
      ])
    );

    const response = await validateLicense(
      request({
        licenseKey: "ABCD-EFGH-IJKL-MNOP",
        deviceId: deviceFingerprint,
        deviceName: "Known workstation"
      })
    );
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body).toMatchObject({
      valid: true,
      remainingActivations: 3,
      deviceAuthorized: false,
      requiresActivation: true
    });
    expect(db.deviceCreate).not.toHaveBeenCalled();
    expect(db.deviceUpdate).not.toHaveBeenCalled();
  });
});
