import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { requireApiUser } from "@/lib/auth";
import { prisma } from "@/lib/db";
import { getClientIpHash, jsonError, requireSameOrigin, validationError } from "@/lib/http";
import { sanitizeLicenseForApi } from "@/lib/license-api";

const statusSchema = z.object({
  status: z.enum(["ACTIVE", "EXPIRED", "SUSPENDED", "REVOKED"])
});

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
    const payload = statusSchema.parse(await request.json());
    const license = await prisma.license.update({
      where: { id },
      data: { status: payload.status },
      include: licenseInclude
    });

    await prisma.auditLog.create({
      data: {
        actorId: user.id,
        action: `LICENSE_${payload.status}`,
        target: license.publicId,
        metadata: { status: payload.status },
        ipHash: getClientIpHash(request)
      }
    });

    return NextResponse.json({ license: sanitizeLicenseForApi(license) });
  } catch (error) {
    return validationError(error);
  }
}
