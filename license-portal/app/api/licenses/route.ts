import { NextResponse } from "next/server";
import { requireApiUser } from "@/lib/auth";
import { prisma } from "@/lib/db";
import { jsonError } from "@/lib/http";
import { customerLicenseForApiSelect, sanitizeLicenseForApi } from "@/lib/license-api";

export async function GET() {
  const user = await requireApiUser();

  if (!user) {
    return jsonError("Non authentifie.", 401);
  }

  const licenses = await prisma.license.findMany({
    where: { ownerId: user.id },
    orderBy: { createdAt: "desc" },
    select: customerLicenseForApiSelect
  });

  return NextResponse.json({ licenses: licenses.map(sanitizeLicenseForApi) });
}
