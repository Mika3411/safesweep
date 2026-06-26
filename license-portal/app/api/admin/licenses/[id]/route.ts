import { NextRequest, NextResponse } from "next/server";
import { Prisma } from "@prisma/client";
import { z } from "zod";
import { requireApiUser } from "@/lib/auth";
import { prisma } from "@/lib/db";
import { getClientIpHash, jsonError, requireSameOrigin, validationError } from "@/lib/http";
import { sanitizeLicenseForApi } from "@/lib/license-api";

const updateLicenseSchema = z.object({
  userId: z.string().uuid().optional(),
  product: z.enum(["ENDPOINT", "SERVER", "MOBILE"]).optional(),
  status: z.enum(["ACTIVE", "EXPIRED", "SUSPENDED", "REVOKED"]).optional(),
  expiresAt: z.string().min(10).optional(),
  deviceLimit: z.number().int().min(1).max(500).optional(),
  maxActivations: z.number().int().min(1).max(500).optional(),
  seatCount: z.number().int().min(1).max(500).optional()
});

function adminLicenseWhere(id: string) {
  if (z.string().uuid().safeParse(id).success) {
    return {
      OR: [{ id }, { publicId: id }]
    };
  }

  return { publicId: id };
}

const licenseInclude = {
  owner: { select: { id: true, name: true, email: true, company: true } },
  devices: { orderBy: { activatedAt: "desc" as const } },
  invoices: { orderBy: { createdAt: "desc" as const } }
};

export async function PATCH(
  request: NextRequest,
  context: { params: Promise<{ id: string }> }
) {
  const csrfError = requireSameOrigin(request);

  if (csrfError) {
    return csrfError;
  }

  const user = await requireApiUser();

  if (!user || user.role !== "ADMIN") {
    return jsonError("Acces admin requis.", 403);
  }

  try {
    const { id } = await context.params;
    const payload = updateLicenseSchema.parse(await request.json());
    const existing = await prisma.license.findFirst({ where: adminLicenseWhere(id) });

    if (!existing) {
      return jsonError("Licence introuvable.", 404);
    }

    const updateData: Prisma.LicenseUpdateInput = {};

    if (payload.userId) {
      const owner = await prisma.user.findUnique({ where: { id: payload.userId } });

      if (!owner) {
        return jsonError("Client introuvable.", 404);
      }

      updateData.owner = { connect: { id: payload.userId } };
    }

    if (payload.product) {
      updateData.product = payload.product;
    }

    if (payload.status) {
      updateData.status = payload.status;
    }

    if (payload.expiresAt) {
      const expiresAt = new Date(payload.expiresAt);

      if (Number.isNaN(expiresAt.getTime())) {
        return jsonError("Date d'expiration invalide.", 422);
      }

      updateData.expiresAt = expiresAt;
    }

    const maxActivations = payload.maxActivations ?? payload.deviceLimit;

    if (maxActivations) {
      updateData.deviceLimit = maxActivations;
    }

    if (payload.seatCount) {
      updateData.seatCount = payload.seatCount;
    }

    if (Object.keys(updateData).length === 0) {
      return jsonError("Aucun champ modifiable fourni.", 400);
    }

    const license = await prisma.$transaction(async (tx) => {
      const updated = await tx.license.update({
        where: { id: existing.id },
        data: updateData,
        include: licenseInclude
      });

      await tx.auditLog.create({
        data: {
          actorId: user.id,
          action: "LICENSE_UPDATED",
          target: updated.publicId,
          metadata: payload,
          ipHash: getClientIpHash(request)
        }
      });

      return updated;
    });

    return NextResponse.json({ license: sanitizeLicenseForApi(license) });
  } catch (error) {
    return validationError(error);
  }
}

export async function DELETE(
  request: NextRequest,
  context: { params: Promise<{ id: string }> }
) {
  const csrfError = requireSameOrigin(request);

  if (csrfError) {
    return csrfError;
  }

  const user = await requireApiUser();

  if (!user || user.role !== "ADMIN") {
    return jsonError("Acces admin requis.", 403);
  }

  const { id } = await context.params;
  const existing = await prisma.license.findFirst({ where: adminLicenseWhere(id) });

  if (!existing) {
    return jsonError("Licence introuvable.", 404);
  }

  const license = await prisma.$transaction(async (tx) => {
    const now = new Date();

    await tx.device.updateMany({
      where: { licenseId: existing.id, deactivatedAt: null },
      data: { deactivatedAt: now, lastSeenAt: now }
    });

    const revoked = await tx.license.update({
      where: { id: existing.id },
      data: { status: "REVOKED" },
      include: licenseInclude
    });

    await tx.auditLog.create({
      data: {
        actorId: user.id,
        action: "LICENSE_REVOKED_BY_DELETE",
        target: revoked.publicId,
        metadata: { requestedMethod: "DELETE", deletionMode: "logical_revoke" },
        ipHash: getClientIpHash(request)
      }
    });

    return revoked;
  });

  return NextResponse.json({
    ok: true,
    deleted: false,
    deletionMode: "logical_revoke",
    license: sanitizeLicenseForApi(license)
  });
}
