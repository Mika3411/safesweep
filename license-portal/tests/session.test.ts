import { SignJWT } from "jose";
import { describe, expect, it } from "vitest";
import { getAuthSecret } from "@/lib/env";
import { createSessionToken, verifySessionToken } from "@/lib/session";

function secretKey() {
  return new TextEncoder().encode(getAuthSecret());
}

describe("session tokens", () => {
  it("round-trips the session version", async () => {
    const token = await createSessionToken({
      userId: "user-id",
      email: "client@safesweep.test",
      name: "Client",
      role: "CUSTOMER",
      sessionVersion: 3
    });

    await expect(verifySessionToken(token)).resolves.toMatchObject({
      userId: "user-id",
      sessionVersion: 3
    });
  });

  it("rejects legacy tokens without a session version", async () => {
    const legacyToken = await new SignJWT({
      userId: "user-id",
      email: "client@safesweep.test",
      name: "Client",
      role: "CUSTOMER"
    })
      .setProtectedHeader({ alg: "HS256" })
      .setIssuedAt()
      .setExpirationTime("7d")
      .sign(secretKey());

    await expect(verifySessionToken(legacyToken)).resolves.toBeNull();
  });
});
