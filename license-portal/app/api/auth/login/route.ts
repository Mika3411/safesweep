import { NextRequest } from "next/server";
import { z } from "zod";
import { createAuthResponse, verifyPassword } from "@/lib/auth";
import { prisma } from "@/lib/db";
import { getClientIp, jsonError, requireSameOrigin, validationError } from "@/lib/http";
import { checkRateLimit } from "@/lib/rate-limit";

const loginSchema = z.object({
  email: z.string().email().toLowerCase(),
  password: z.string().min(1)
});

export async function POST(request: NextRequest) {
  const csrfError = requireSameOrigin(request);

  if (csrfError) {
    return csrfError;
  }

  const rate = await checkRateLimit({
    key: `auth:login:${getClientIp(request)}`,
    limit: 8,
    windowMs: 15 * 60 * 1000
  });

  if (!rate.allowed) {
    return jsonError(
      rate.unavailable ? "Rate limit indisponible." : "Trop de tentatives. Reessayez plus tard.",
      rate.unavailable ? 503 : 429
    );
  }

  try {
    const payload = loginSchema.parse(await request.json());
    const user = await prisma.user.findUnique({ where: { email: payload.email } });

    if (!user || !(await verifyPassword(payload.password, user.passwordHash))) {
      return jsonError("Identifiants invalides.", 401);
    }

    return createAuthResponse(
      {
        userId: user.id,
        email: user.email,
        name: user.name,
        role: user.role,
        sessionVersion: user.sessionVersion
      },
      { ok: true, redirectTo: user.role === "ADMIN" ? "/admin" : "/dashboard" }
    );
  } catch (error) {
    return validationError(error);
  }
}
