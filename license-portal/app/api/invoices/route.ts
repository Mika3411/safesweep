import { NextResponse } from "next/server";
import { requireApiUser } from "@/lib/auth";
import { prisma } from "@/lib/db";
import { jsonError } from "@/lib/http";

export async function GET() {
  const user = await requireApiUser();

  if (!user) {
    return jsonError("Non authentifie.", 401);
  }

  const invoices = await prisma.invoice.findMany({
    where: { userId: user.id },
    orderBy: { createdAt: "desc" }
  });

  return NextResponse.json({ invoices });
}
