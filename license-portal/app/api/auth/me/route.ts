import { NextRequest, NextResponse } from "next/server";
import { Prisma } from "@prisma/client";
import { z } from "zod";
import { createAuthResponse, getCurrentUser, hashPassword, verifyPassword } from "@/lib/auth";
import { prisma } from "@/lib/db";
import { getClientIpHash, jsonError, requireSameOrigin, validationError } from "@/lib/http";

const updateAccountSchema = z.object({
  name: z.string().min(2).max(120).optional(),
  company: z.string().min(2).max(160).nullable().optional(),
  currentPassword: z.string().optional(),
  newPassword: z.string().min(10).optional()
});

export async function GET() {
  const user = await getCurrentUser();

  if (!user) {
    return jsonError("Non authentifie.", 401);
  }

  return NextResponse.json({ user });
}

export async function PATCH(request: NextRequest) {
  const csrfError = requireSameOrigin(request);

  if (csrfError) {
    return csrfError;
  }

  const user = await getCurrentUser();

  if (!user) {
    return jsonError("Non authentifie.", 401);
  }

  try {
    const payload = updateAccountSchema.parse(await request.json());
    const data: Prisma.UserUpdateInput = {};
    let passwordChanged = false;

    if (payload.name) {
      data.name = payload.name;
    }

    if (payload.company !== undefined) {
      data.company = payload.company;
    }

    if (payload.newPassword) {
      if (!payload.currentPassword) {
        return jsonError("Mot de passe actuel requis.", 400);
      }

      const fullUser = await prisma.user.findUnique({ where: { id: user.id } });

      if (!fullUser || !(await verifyPassword(payload.currentPassword, fullUser.passwordHash))) {
        return jsonError("Mot de passe actuel incorrect.", 403);
      }

      data.passwordHash = await hashPassword(payload.newPassword);
      data.sessionVersion = { increment: 1 };
      passwordChanged = true;
    }

    if (Object.keys(data).length === 0) {
      return jsonError("Aucune modification fournie.", 400);
    }

    const [updated] = await prisma.$transaction([
      prisma.user.update({
        where: { id: user.id },
        data,
        select: {
          id: true,
          email: true,
          name: true,
          company: true,
          role: true,
          stripeCustomerId: true,
          sessionVersion: true
        }
      }),
      prisma.auditLog.create({
        data: {
          actorId: user.id,
          action: "ACCOUNT_UPDATED",
          target: user.id,
          metadata: {
            changedFields: Object.keys(data).filter((field) => field !== "passwordHash" && field !== "sessionVersion"),
            passwordChanged: Boolean(data.passwordHash)
          },
          ipHash: getClientIpHash(request)
        }
      })
    ]);

    const { sessionVersion, ...safeUser } = updated;

    if (passwordChanged) {
      return createAuthResponse(
        {
          userId: updated.id,
          email: updated.email,
          name: updated.name,
          role: updated.role,
          sessionVersion
        },
        { user: safeUser }
      );
    }

    return NextResponse.json({ user: safeUser });
  } catch (error) {
    return validationError(error);
  }
}
