import { NextResponse } from "next/server";
import { z } from "zod";
import { requireApiUser } from "@/lib/auth";
import { prisma } from "@/lib/db";
import { jsonError } from "@/lib/http";
import { customerLicenseForApiSelect, sanitizeLicenseForApi } from "@/lib/license-api";

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

export async function GET(_request: Request, context: { params: Promise<{ id: string }> }) {
  const user = await requireApiUser();

  if (!user) {
    return jsonError("Non authentifie.", 401);
  }

  const { id } = await context.params;
  const license = await prisma.license.findFirst({
    where: licenseWhere(id, user.id),
    select: customerLicenseForApiSelect
  });

  if (!license) {
    return jsonError("Licence introuvable.", 404);
  }

  return NextResponse.json({ license: sanitizeLicenseForApi(license) });
}
