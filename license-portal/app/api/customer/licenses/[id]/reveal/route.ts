import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { requireApiUser } from "@/lib/auth";
import { prisma } from "@/lib/db";
import { getClientIpHash, jsonError, requireSameOrigin } from "@/lib/http";
import { decryptLicenseKey } from "@/lib/license-key-delivery";

function licenseWhere(id: string, ownerId: string) {
  if (z.string().uuid().safeParse(id).success) {
    return {
      ownerId,
      OR: [{ id }, { publicId: id }]
    };
  }

  return {
    ownerId,
    publicId: id
  };
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ id: string }> }
) {
  const csrfError = requireSameOrigin(request);

  if (csrfError) {
    return csrfError;
  }

  const user = await requireApiUser();

  if (!user) {
    return jsonError("Non authentifie.", 401);
  }

  const { id } = await context.params;
  const license = await prisma.license.findFirst({
    where: licenseWhere(id, user.id),
    select: {
      id: true,
      publicId: true,
      keyPrefix: true,
      encryptedLicenseKey: true,
      licenseKeyRevealedAt: true
    }
  });

  if (!license) {
    return jsonError("Licence introuvable.", 404);
  }

  if (!license.encryptedLicenseKey || license.licenseKeyRevealedAt) {
    await prisma.auditLog.create({
      data: {
        actorId: user.id,
        action: "LICENSE_KEY_REVEAL_DENIED",
        target: license.publicId,
        metadata: {
          reason: license.licenseKeyRevealedAt ? "already_revealed" : "not_available",
          keyPrefix: license.keyPrefix
        },
        ipHash: getClientIpHash(request)
      }
    });

    return jsonError("Cle de licence deja revelee ou indisponible.", 409);
  }

  let licenseKey: string;

  try {
    licenseKey = decryptLicenseKey(license.encryptedLicenseKey);
  } catch {
    await prisma.auditLog.create({
      data: {
        actorId: user.id,
        action: "LICENSE_KEY_REVEAL_FAILED",
        target: license.publicId,
        metadata: { reason: "decrypt_failed", keyPrefix: license.keyPrefix },
        ipHash: getClientIpHash(request)
      }
    });

    return jsonError("Cle de licence indisponible.", 500);
  }

  const revealedAt = new Date();
  const revealed = await prisma.$transaction(async (tx) => {
    const update = await tx.license.updateMany({
      where: {
        id: license.id,
        encryptedLicenseKey: { not: null },
        licenseKeyRevealedAt: null
      },
      data: {
        encryptedLicenseKey: null,
        licenseKeyRevealedAt: revealedAt
      }
    });

    if (update.count !== 1) {
      return false;
    }

    await tx.auditLog.create({
      data: {
        actorId: user.id,
        action: "LICENSE_KEY_REVEALED",
        target: license.publicId,
        metadata: {
          keyPrefix: license.keyPrefix,
          delivery: "one_time"
        },
        ipHash: getClientIpHash(request)
      }
    });

    return true;
  });

  if (!revealed) {
    return jsonError("Cle de licence deja revelee ou indisponible.", 409);
  }

  return NextResponse.json({
    licenseKey,
    revealedAt: revealedAt.toISOString()
  });
}
