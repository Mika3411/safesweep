import { NextResponse } from "next/server";
import { requireApiUser } from "@/lib/auth";
import { prisma } from "@/lib/db";
import { jsonError } from "@/lib/http";

export async function GET() {
  const user = await requireApiUser();

  if (!user || user.role !== "ADMIN") {
    return jsonError("Acces admin requis.", 403);
  }

  const payments = await prisma.payment.findMany({
    orderBy: { createdAt: "desc" },
    include: {
      user: { select: { name: true, company: true, email: true } }
    },
    take: 100
  });

  return NextResponse.json({ payments });
}
