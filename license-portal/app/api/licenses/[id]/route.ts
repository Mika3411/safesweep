import { NextResponse } from "next/server";
import { requireApiUser } from "@/lib/auth";
import { prisma } from "@/lib/db";
import { jsonError } from "@/lib/http";
import { customerLicenseForApiSelect, sanitizeLicenseForApi } from "@/lib/license-api";

export async function GET(_request: Request, context: { params: Promise<{ id: string }> }) {
  const user = await requireApiUser();

  if (!user) {
    return jsonError("Non authentifie.", 401);
  }

  const { id } = await context.params;
  const license = await prisma.license.findFirst({
    where: { id, ownerId: user.id },
    select: customerLicenseForApiSelect
  });

  if (!license) {
    return jsonError("Licence introuvable.", 404);
  }

  return NextResponse.json({ license: sanitizeLicenseForApi(license) });
}
