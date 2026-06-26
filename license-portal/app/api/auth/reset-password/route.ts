import crypto from "node:crypto";
import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { hashPassword } from "@/lib/auth";
import { prisma } from "@/lib/db";
import { getClientIp, jsonError, requireSameOrigin, validationError } from "@/lib/http";
import { checkRateLimit } from "@/lib/rate-limit";

const resetSchema = z.object({
  token: z.string().min(32),
  password: z.string().min(10)
});

export async function POST(request: NextRequest) {
  const csrfError = requireSameOrigin(request);

  if (csrfError) {
    return csrfError;
  }

  const rate = await checkRateLimit({
    key: `auth:reset:${getClientIp(request)}`,
    limit: 8,
    windowMs: 30 * 60 * 1000
  });

  if (!rate.allowed) {
    return jsonError(
      rate.unavailable ? "Rate limit indisponible." : "Trop de tentatives. Reessayez plus tard.",
      rate.unavailable ? 503 : 429
    );
  }

  try {
    const payload = resetSchema.parse(await request.json());
    const tokenHash = crypto.createHash("sha256").update(payload.token).digest("hex");
    const user = await prisma.user.findFirst({
      where: {
        passwordResetTokenHash: tokenHash,
        passwordResetTokenExpiry: { gt: new Date() }
      }
    });

    if (!user) {
      return jsonError("Lien de reinitialisation invalide ou expire.", 400);
    }

    await prisma.user.update({
      where: { id: user.id },
      data: {
        passwordHash: await hashPassword(payload.password),
        sessionVersion: { increment: 1 },
        passwordResetTokenHash: null,
        passwordResetTokenExpiry: null
      }
    });

    return NextResponse.json({ ok: true });
  } catch (error) {
    return validationError(error);
  }
}
