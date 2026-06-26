import crypto from "node:crypto";
import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { prisma } from "@/lib/db";
import { getAppUrl } from "@/lib/env";
import { getClientIp, jsonError, requireSameOrigin, validationError } from "@/lib/http";
import { checkRateLimit } from "@/lib/rate-limit";

const forgotSchema = z.object({
  email: z.string().email().toLowerCase()
});

export async function POST(request: NextRequest) {
  const csrfError = requireSameOrigin(request);

  if (csrfError) {
    return csrfError;
  }

  const rate = await checkRateLimit({
    key: `auth:forgot:${getClientIp(request)}`,
    limit: 5,
    windowMs: 30 * 60 * 1000
  });

  if (rate.unavailable) {
    return jsonError("Rate limit indisponible.", 503);
  }

  if (!rate.allowed) {
    return NextResponse.json({ ok: true });
  }

  try {
    const { email } = forgotSchema.parse(await request.json());
    const token = crypto.randomBytes(32).toString("hex");
    const tokenHash = crypto.createHash("sha256").update(token).digest("hex");
    const expiresAt = new Date(Date.now() + 1000 * 60 * 30);

    await prisma.user.updateMany({
      where: { email },
      data: {
        passwordResetTokenHash: tokenHash,
        passwordResetTokenExpiry: expiresAt
      }
    });

    const body: { ok: true; resetUrl?: string } = { ok: true };

    if (process.env.NODE_ENV !== "production") {
      body.resetUrl = `${getAppUrl()}/reset-password/${token}`;
    }

    return NextResponse.json(body);
  } catch (error) {
    return validationError(error);
  }
}
