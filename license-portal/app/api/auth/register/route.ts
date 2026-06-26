import { NextRequest } from "next/server";
import { z } from "zod";
import { createAuthResponse, hashPassword } from "@/lib/auth";
import { prisma } from "@/lib/db";
import { getClientIp, jsonError, requireSameOrigin, validationError } from "@/lib/http";
import { checkRateLimit } from "@/lib/rate-limit";

const registerSchema = z.object({
  name: z.string().min(2),
  company: z.string().min(2).optional(),
  email: z.string().email().toLowerCase(),
  password: z.string().min(10)
});

export async function POST(request: NextRequest) {
  const csrfError = requireSameOrigin(request);

  if (csrfError) {
    return csrfError;
  }

  const rate = await checkRateLimit({
    key: `auth:register:${getClientIp(request)}`,
    limit: 10,
    windowMs: 15 * 60 * 1000
  });

  if (!rate.allowed) {
    return jsonError(
      rate.unavailable ? "Rate limit indisponible." : "Trop de tentatives. Reessayez plus tard.",
      rate.unavailable ? 503 : 429
    );
  }

  try {
    const payload = registerSchema.parse(await request.json());
    const existingUser = await prisma.user.findUnique({ where: { email: payload.email } });

    if (existingUser) {
      return jsonError("Un compte existe deja avec cet e-mail.", 409);
    }

    const user = await prisma.user.create({
      data: {
        name: payload.name,
        company: payload.company,
        email: payload.email,
        passwordHash: await hashPassword(payload.password)
      }
    });

    return createAuthResponse(
      {
        userId: user.id,
        email: user.email,
        name: user.name,
        role: user.role,
        sessionVersion: user.sessionVersion
      },
      { ok: true, redirectTo: "/dashboard" }
    );
  } catch (error) {
    return validationError(error);
  }
}
