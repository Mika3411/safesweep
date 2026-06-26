import { NextRequest, NextResponse } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createSessionToken, SESSION_COOKIE } from "@/lib/session";

const mocks = vi.hoisted(() => ({
  cookieGet: vi.fn(),
  userFindUnique: vi.fn(),
  userFindFirst: vi.fn(),
  userUpdate: vi.fn(),
  auditLogCreate: vi.fn(),
  transaction: vi.fn(),
  hashPassword: vi.fn(),
  verifyPassword: vi.fn(),
  createAuthResponse: vi.fn(),
  checkRateLimit: vi.fn()
}));

vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: mocks.cookieGet
  })
}));

vi.mock("@/lib/db", () => ({
  prisma: {
    user: {
      findUnique: mocks.userFindUnique,
      findFirst: mocks.userFindFirst,
      update: mocks.userUpdate
    },
    auditLog: {
      create: mocks.auditLogCreate
    },
    $transaction: mocks.transaction
  }
}));

vi.mock("@/lib/rate-limit", () => ({
  checkRateLimit: mocks.checkRateLimit
}));

vi.mock("@/lib/auth", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/auth")>();

  return {
    ...actual,
    hashPassword: mocks.hashPassword,
    verifyPassword: mocks.verifyPassword,
    createAuthResponse: mocks.createAuthResponse
  };
});

import { getCurrentUser } from "@/lib/auth";
import { PATCH as updateMe } from "@/app/api/auth/me/route";
import { POST as resetPassword } from "@/app/api/auth/reset-password/route";

function request(path: string, body: Record<string, unknown>) {
  return new NextRequest(`https://portal.example${path}`, {
    method: "POST",
    headers: {
      host: "portal.example",
      origin: "https://portal.example",
      "content-type": "application/json"
    },
    body: JSON.stringify(body)
  });
}

describe("session invalidation", () => {
  beforeEach(() => {
    process.env.APP_URL = "https://portal.example";
    vi.clearAllMocks();
    mocks.hashPassword.mockResolvedValue("new-password-hash");
    mocks.verifyPassword.mockResolvedValue(true);
    mocks.createAuthResponse.mockResolvedValue(NextResponse.json({ ok: true }));
    mocks.checkRateLimit.mockResolvedValue({
      allowed: true,
      remaining: 7,
      resetAt: Date.now() + 60_000
    });
    mocks.auditLogCreate.mockResolvedValue({});
    mocks.transaction.mockImplementation(async (items) => Promise.all(items));
  });

  it("rejects a JWT when the stored session version has changed", async () => {
    const token = await createSessionToken({
      userId: "user-id",
      email: "client@safesweep.test",
      name: "Client",
      role: "CUSTOMER",
      sessionVersion: 1
    });

    mocks.cookieGet.mockReturnValue({ name: SESSION_COOKIE, value: token });
    mocks.userFindUnique.mockResolvedValue({
      id: "user-id",
      email: "client@safesweep.test",
      name: "Client",
      company: null,
      role: "CUSTOMER",
      stripeCustomerId: null,
      sessionVersion: 2
    });

    await expect(getCurrentUser()).resolves.toBeNull();
  });

  it("increments sessionVersion after an authenticated password change and issues a fresh session", async () => {
    const token = await createSessionToken({
      userId: "user-id",
      email: "client@safesweep.test",
      name: "Client",
      role: "CUSTOMER",
      sessionVersion: 1
    });

    mocks.cookieGet.mockReturnValue({ name: SESSION_COOKIE, value: token });
    mocks.userFindUnique
      .mockResolvedValueOnce({
        id: "user-id",
        email: "client@safesweep.test",
        name: "Client",
        company: null,
        role: "CUSTOMER",
        stripeCustomerId: null,
        sessionVersion: 1
      })
      .mockResolvedValueOnce({
        id: "user-id",
        passwordHash: "old-password-hash"
      });
    mocks.userUpdate.mockResolvedValue({
      id: "user-id",
      email: "client@safesweep.test",
      name: "Client",
      company: null,
      role: "CUSTOMER",
      stripeCustomerId: null,
      sessionVersion: 2
    });

    await updateMe(
      new NextRequest("https://portal.example/api/auth/me", {
        method: "PATCH",
        headers: {
          host: "portal.example",
          origin: "https://portal.example",
          "content-type": "application/json"
        },
        body: JSON.stringify({
          currentPassword: "old-password",
          newPassword: "new-password-123"
        })
      })
    );

    expect(mocks.userUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({
          passwordHash: "new-password-hash",
          sessionVersion: { increment: 1 }
        })
      })
    );
    expect(mocks.createAuthResponse).toHaveBeenCalledWith(
      expect.objectContaining({
        userId: "user-id",
        sessionVersion: 2
      }),
      expect.any(Object)
    );
  });

  it("increments sessionVersion after password reset", async () => {
    mocks.userFindFirst.mockResolvedValue({
      id: "user-id",
      passwordResetTokenHash: "token-hash",
      passwordResetTokenExpiry: new Date(Date.now() + 60_000)
    });
    mocks.userUpdate.mockResolvedValue({});

    const response = await resetPassword(
      request("/api/auth/reset-password", {
        token: "a".repeat(32),
        password: "new-password-123"
      })
    );

    expect(response.status).toBe(200);
    expect(mocks.userUpdate).toHaveBeenCalledWith({
      where: { id: "user-id" },
      data: {
        passwordHash: "new-password-hash",
        sessionVersion: { increment: 1 },
        passwordResetTokenHash: null,
        passwordResetTokenExpiry: null
      }
    });
  });
});
