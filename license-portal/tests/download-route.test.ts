import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  requireApiUser: vi.fn(),
  licenseCount: vi.fn()
}));

vi.mock("@/lib/auth", () => ({
  requireApiUser: mocks.requireApiUser
}));

vi.mock("@/lib/db", () => ({
  prisma: {
    license: {
      count: mocks.licenseCount
    }
  }
}));

import { GET } from "@/app/api/downloads/software/route";

describe("software download route", () => {
  beforeEach(() => {
    process.env.SOFTWARE_DOWNLOAD_URL = "https://downloads.example.com/safesweep/latest";
    vi.clearAllMocks();
    mocks.requireApiUser.mockResolvedValue({
      id: "user-id",
      email: "client@safesweep.test",
      name: "Client",
      role: "CUSTOMER"
    });
  });

  it("rejects authenticated users without an active license", async () => {
    mocks.licenseCount.mockResolvedValue(0);

    const response = await GET();

    expect(response.status).toBe(403);
    await expect(response.json()).resolves.toMatchObject({
      error: "Aucune licence active ne permet ce telechargement."
    });
  });

  it("redirects users with an active license", async () => {
    mocks.licenseCount.mockResolvedValue(1);

    const response = await GET();

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("https://downloads.example.com/safesweep/latest");
    expect(mocks.licenseCount).toHaveBeenCalledWith({
      where: {
        ownerId: "user-id",
        status: "ACTIVE",
        expiresAt: { gt: expect.any(Date) }
      }
    });
  });
});
