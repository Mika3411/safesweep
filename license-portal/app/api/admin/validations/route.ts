import { NextResponse } from "next/server";
import { requireApiUser } from "@/lib/auth";
import { prisma } from "@/lib/db";
import { jsonError } from "@/lib/http";
import { serializeValidation } from "@/lib/serializers";

export async function GET() {
  const user = await requireApiUser();

  if (!user || user.role !== "ADMIN") {
    return jsonError("Acces admin requis.", 403);
  }

  const validations = await prisma.licenseValidation.findMany({
    orderBy: { createdAt: "desc" },
    select: {
      id: true,
      createdAt: true,
      action: true,
      result: true,
      reason: true,
      license: { select: { publicId: true, product: true } },
      device: { select: { name: true, platform: true } }
    },
    take: 100
  });

  return NextResponse.json({ validations: validations.map(serializeValidation) });
}
