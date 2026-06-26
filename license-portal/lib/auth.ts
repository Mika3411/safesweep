import bcrypt from "bcryptjs";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { createSessionToken, SESSION_COOKIE, SessionUser, verifySessionToken } from "@/lib/session";

export async function hashPassword(password: string) {
  return bcrypt.hash(password, 12);
}

export async function verifyPassword(password: string, hash: string) {
  return bcrypt.compare(password, hash);
}

export async function getCurrentUser() {
  const cookieStore = await cookies();
  const session = await verifySessionToken(cookieStore.get(SESSION_COOKIE)?.value);

  if (!session) {
    return null;
  }

  const user = await prisma.user.findUnique({
    where: { id: session.userId },
    select: {
      id: true,
      email: true,
      name: true,
      company: true,
      role: true,
      stripeCustomerId: true,
      sessionVersion: true
    }
  });

  if (!user || user.sessionVersion !== session.sessionVersion) {
    return null;
  }

  const { sessionVersion, ...safeUser } = user;

  return safeUser;
}

export async function requireUser() {
  const user = await getCurrentUser();

  if (!user) {
    redirect("/login");
  }

  return user;
}

export async function requireAdmin() {
  const user = await requireUser();

  if (user.role !== "ADMIN") {
    redirect("/dashboard");
  }

  return user;
}

export async function requireApiUser() {
  const user = await getCurrentUser();

  if (!user) {
    return null;
  }

  return user;
}

export async function createAuthResponse(user: SessionUser, body: Record<string, unknown> = { ok: true }) {
  const response = NextResponse.json(body);
  const token = await createSessionToken(user);

  response.cookies.set(SESSION_COOKIE, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 7
  });

  return response;
}

export function clearAuthResponse() {
  const response = NextResponse.json({ ok: true });

  response.cookies.set(SESSION_COOKIE, "", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 0
  });

  return response;
}
