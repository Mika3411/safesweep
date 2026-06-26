import { SignJWT, jwtVerify } from "jose";
import { getAuthSecret } from "@/lib/env";

export const SESSION_COOKIE = "safesweep_session";

export type SessionRole = "CUSTOMER" | "ADMIN";

export type SessionUser = {
  userId: string;
  email: string;
  name: string;
  role: SessionRole;
  sessionVersion: number;
};

function secretKey() {
  return new TextEncoder().encode(getAuthSecret());
}

export async function createSessionToken(user: SessionUser) {
  return new SignJWT(user)
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime("7d")
    .sign(secretKey());
}

export async function verifySessionToken(token?: string | null) {
  if (!token) {
    return null;
  }

  try {
    const { payload } = await jwtVerify(token, secretKey());

    if (
      typeof payload.userId !== "string" ||
      typeof payload.email !== "string" ||
      typeof payload.name !== "string" ||
      typeof payload.sessionVersion !== "number" ||
      !Number.isInteger(payload.sessionVersion) ||
      (payload.role !== "CUSTOMER" && payload.role !== "ADMIN")
    ) {
      return null;
    }

    return {
      userId: payload.userId,
      email: payload.email,
      name: payload.name,
      role: payload.role,
      sessionVersion: payload.sessionVersion
    } satisfies SessionUser;
  } catch {
    return null;
  }
}
