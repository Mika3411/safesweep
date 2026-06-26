import { NextResponse } from "next/server";
import { requireApiUser } from "@/lib/auth";
import { prisma } from "@/lib/db";
import { jsonError } from "@/lib/http";

export async function GET() {
  const user = await requireApiUser();

  if (!user || user.role !== "ADMIN") {
    return jsonError("Acces admin requis.", 403);
  }

  const customers = await prisma.user.findMany({
    where: { role: "CUSTOMER" },
    orderBy: { createdAt: "desc" },
    select: {
      id: true,
      name: true,
      company: true,
      email: true,
      createdAt: true,
      _count: {
        select: {
          licenses: true,
          payments: true
        }
      }
    }
  });

  return NextResponse.json({ customers });
}
