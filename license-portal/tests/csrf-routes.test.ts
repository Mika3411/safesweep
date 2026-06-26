import { NextRequest, NextResponse } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  clearAuthResponse: vi.fn(),
  createAuthResponse: vi.fn(),
  getCurrentUser: vi.fn(),
  hashPassword: vi.fn(),
  requireApiUser: vi.fn(),
  verifyPassword: vi.fn(),
  prisma: {
    user: {
      findUnique: vi.fn(),
      update: vi.fn()
    },
    license: {
      create: vi.fn(),
      findFirst: vi.fn(),
      update: vi.fn(),
      updateMany: vi.fn()
    },
    device: {
      findFirst: vi.fn(),
      update: vi.fn(),
      updateMany: vi.fn()
    },
    auditLog: {
      create: vi.fn()
    },
    $transaction: vi.fn()
  }
}));

vi.mock("@/lib/auth", () => ({
  clearAuthResponse: mocks.clearAuthResponse,
  createAuthResponse: mocks.createAuthResponse,
  getCurrentUser: mocks.getCurrentUser,
  hashPassword: mocks.hashPassword,
  requireApiUser: mocks.requireApiUser,
  verifyPassword: mocks.verifyPassword
}));

vi.mock("@/lib/db", () => ({
  prisma: mocks.prisma
}));

import { POST as checkout } from "@/app/api/billing/checkout/route";
import { POST as portal } from "@/app/api/billing/portal/route";
import { PATCH as updateMe } from "@/app/api/auth/me/route";
import { POST as logout } from "@/app/api/auth/logout/route";
import { DELETE as deleteDevice } from "@/app/api/licenses/[id]/devices/[deviceId]/route";
import { POST as createAdminLicense } from "@/app/api/admin/licenses/route";
import { POST as revealCustomerLicenseKey } from "@/app/api/customer/licenses/[id]/reveal/route";
import {
  DELETE as deleteAdminLicense,
  PATCH as patchAdminLicense
} from "@/app/api/admin/licenses/[id]/route";
import { PATCH as patchAdminLicenseStatus } from "@/app/api/admin/licenses/[id]/status/route";
import { PATCH as patchAdminLicenseExpiration } from "@/app/api/admin/licenses/[id]/expiration/route";

type RouteCall = {
  name: string;
  call: (request: NextRequest) => Promise<Response>;
};

const originalAppUrl = process.env.APP_URL;
const originalTrustedOrigins = process.env.CSRF_TRUSTED_ORIGINS;

function restoreEnv() {
  if (originalAppUrl === undefined) {
    delete process.env.APP_URL;
  } else {
    process.env.APP_URL = originalAppUrl;
  }

  if (originalTrustedOrigins === undefined) {
    delete process.env.CSRF_TRUSTED_ORIGINS;
  } else {
    process.env.CSRF_TRUSTED_ORIGINS = originalTrustedOrigins;
  }
}

function request(method: string) {
  return new NextRequest("https://portal.example/api/test", {
    method,
    headers: {
      host: "portal.example",
      origin: "https://attacker.example"
    }
  });
}

const licenseContext = { params: Promise.resolve({ id: "license-id" }) };
const deviceContext = { params: Promise.resolve({ id: "license-id", deviceId: "device-id" }) };

const mutatingRoutes: RouteCall[] = [
  { name: "auth/me PATCH", call: (csrfRequest) => updateMe(csrfRequest) },
  { name: "auth/logout POST", call: (csrfRequest) => logout(csrfRequest) },
  { name: "billing/checkout POST", call: (csrfRequest) => checkout(csrfRequest) },
  { name: "billing/portal POST", call: (csrfRequest) => portal(csrfRequest) },
  { name: "licenses device DELETE", call: (csrfRequest) => deleteDevice(csrfRequest, deviceContext) },
  { name: "customer license reveal POST", call: (csrfRequest) => revealCustomerLicenseKey(csrfRequest, licenseContext) },
  { name: "admin licenses POST", call: (csrfRequest) => createAdminLicense(csrfRequest) },
  { name: "admin license PATCH", call: (csrfRequest) => patchAdminLicense(csrfRequest, licenseContext) },
  { name: "admin license DELETE", call: (csrfRequest) => deleteAdminLicense(csrfRequest, licenseContext) },
  { name: "admin license status PATCH", call: (csrfRequest) => patchAdminLicenseStatus(csrfRequest, licenseContext) },
  {
    name: "admin license expiration PATCH",
    call: (csrfRequest) => patchAdminLicenseExpiration(csrfRequest, licenseContext)
  }
];

describe("mutating authenticated routes CSRF protection", () => {
  beforeEach(() => {
    process.env.APP_URL = "https://portal.example";
    delete process.env.CSRF_TRUSTED_ORIGINS;
    vi.clearAllMocks();
    mocks.clearAuthResponse.mockReturnValue(NextResponse.json({ ok: true }));
  });

  afterEach(() => {
    restoreEnv();
  });

  it.each(mutatingRoutes)("rejects unknown origins before side effects: $name", async ({ call }) => {
    const response = await call(request("POST"));

    expect(response.status).toBe(403);
    await expect(response.json()).resolves.toMatchObject({ error: "Origin non autorisee." });
    expect(mocks.getCurrentUser).not.toHaveBeenCalled();
    expect(mocks.requireApiUser).not.toHaveBeenCalled();
    expect(mocks.clearAuthResponse).not.toHaveBeenCalled();
    expect(mocks.prisma.$transaction).not.toHaveBeenCalled();
  });
});
