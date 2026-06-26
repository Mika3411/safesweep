import { NextResponse } from "next/server";
import { requireApiUser } from "@/lib/auth";
import { prisma } from "@/lib/db";
import { getEnv } from "@/lib/env";
import { jsonError } from "@/lib/http";

export async function GET() {
  const user = await requireApiUser();

  if (!user) {
    return jsonError("Non authentifie.", 401);
  }

  const activeLicenseCount = await prisma.license.count({
    where: {
      ownerId: user.id,
      status: "ACTIVE",
      expiresAt: { gt: new Date() }
    }
  });

  if (activeLicenseCount === 0) {
    return jsonError("Aucune licence active ne permet ce telechargement.", 403);
  }

  const downloadUrl = getEnv("SOFTWARE_DOWNLOAD_URL", "https://downloads.example.com/safesweep/latest");
  return NextResponse.redirect(downloadUrl);
}
