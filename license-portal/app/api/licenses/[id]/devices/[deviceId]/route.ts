import { NextRequest, NextResponse } from "next/server";
import { requireApiUser } from "@/lib/auth";
import { prisma } from "@/lib/db";
import { getClientIpHash, jsonError, requireSameOrigin } from "@/lib/http";

export async function DELETE(
  request: NextRequest,
  context: { params: Promise<{ id: string; deviceId: string }> }
) {
  const csrfError = requireSameOrigin(request);

  if (csrfError) {
    return csrfError;
  }

  const user = await requireApiUser();

  if (!user) {
    return jsonError("Non authentifie.", 401);
  }

  const { id, deviceId } = await context.params;
  const device = await prisma.device.findFirst({
    where: {
      id: deviceId,
      license: {
        id,
        ownerId: user.id
      }
    },
    include: { license: true }
  });

  if (!device) {
    return jsonError("Appareil introuvable.", 404);
  }

  await prisma.$transaction([
    prisma.device.update({
      where: { id: device.id },
      data: { deactivatedAt: new Date() }
    }),
    prisma.auditLog.create({
      data: {
        actorId: user.id,
        action: "DEVICE_DEACTIVATED",
        target: device.license.publicId,
        metadata: { deviceId: device.id, deviceName: device.name },
        ipHash: getClientIpHash(request)
      }
    })
  ]);

  return NextResponse.json({ ok: true });
}
