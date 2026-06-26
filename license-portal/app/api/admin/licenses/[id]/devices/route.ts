import { NextResponse } from "next/server";
import { requireApiUser } from "@/lib/auth";
import { prisma } from "@/lib/db";
import { jsonError } from "@/lib/http";
import { serializeDevice } from "@/lib/serializers";

export async function GET(_request: Request, context: { params: Promise<{ id: string }> }) {
  const user = await requireApiUser();

  if (!user || user.role !== "ADMIN") {
    return jsonError("Acces admin requis.", 403);
  }

  const { id } = await context.params;
  const devices = await prisma.device.findMany({
    where: { licenseId: id },
    orderBy: { activatedAt: "desc" },
    select: {
      id: true,
      name: true,
      platform: true,
      activatedAt: true,
      deactivatedAt: true,
      lastSeenAt: true
    }
  });

  return NextResponse.json({ devices: devices.map(serializeDevice) });
}
