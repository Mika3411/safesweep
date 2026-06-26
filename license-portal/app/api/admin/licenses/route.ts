import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { requireApiUser } from "@/lib/auth";
import { prisma } from "@/lib/db";
import { getClientIpHash, jsonError, requireSameOrigin, validationError } from "@/lib/http";
import { buildPublicLicenseId, generateLicenseKey, hashLicenseKey } from "@/lib/license";
import { sanitizeLicenseForApi } from "@/lib/license-api";

const createLicenseSchema = z.object({
  userId: z.string().uuid(),
  product: z.enum(["ENDPOINT", "SERVER", "MOBILE"]),
  deviceLimit: z.number().int().min(1).max(500).optional(),
  maxActivations: z.number().int().min(1).max(500).optional(),
  seatCount: z.number().int().min(1).max(500).optional(),
  expiresAt: z.string().min(10),
  status: z.enum(["ACTIVE", "EXPIRED", "SUSPENDED", "REVOKED"]).optional()
});

export async function GET() {
  const user = await requireApiUser();

  if (!user || user.role !== "ADMIN") {
    return jsonError("Acces admin requis.", 403);
  }

  const licenses = await prisma.license.findMany({
    orderBy: { createdAt: "desc" },
    include: {
      owner: { select: { id: true, name: true, email: true, company: true } },
      devices: { orderBy: { activatedAt: "desc" } },
      invoices: { orderBy: { createdAt: "desc" } }
    },
    take: 100
  });

  return NextResponse.json({ licenses: licenses.map(sanitizeLicenseForApi) });
}

export async function POST(request: NextRequest) {
  const csrfError = requireSameOrigin(request);

  if (csrfError) {
    return csrfError;
  }

  const user = await requireApiUser();

  if (!user || user.role !== "ADMIN") {
    return jsonError("Acces admin requis.", 403);
  }

  try {
    const payload = createLicenseSchema.parse(await request.json());
    const owner = await prisma.user.findUnique({ where: { id: payload.userId } });
    const expiresAt = new Date(payload.expiresAt);

    if (!owner) {
      return jsonError("Client introuvable.", 404);
    }

    if (Number.isNaN(expiresAt.getTime())) {
      return jsonError("Date d'expiration invalide.", 422);
    }

    const licenseCount = await prisma.license.count();
    const rawKey = generateLicenseKey();
    const publicId = buildPublicLicenseId(owner.company ?? owner.name, licenseCount + 1);
    const maxActivations = payload.maxActivations ?? payload.deviceLimit ?? 1;

    const license = await prisma.license.create({
      data: {
        publicId,
        keyHash: hashLicenseKey(rawKey),
        keyPrefix: rawKey.split("-")[0],
        product: payload.product,
        status: payload.status ?? "ACTIVE",
        deviceLimit: maxActivations,
        seatCount: payload.seatCount ?? maxActivations,
        expiresAt,
        ownerId: owner.id,
        validations: {
          create: {
            action: "CREATED",
            result: "ALLOWED",
            reason: `Licence creee par ${user.email}`
          }
        }
      },
      include: {
        owner: { select: { id: true, name: true, email: true, company: true } },
        devices: { orderBy: { activatedAt: "desc" } },
        invoices: { orderBy: { createdAt: "desc" } }
      }
    });

    await prisma.auditLog.create({
      data: {
        actorId: user.id,
        action: "LICENSE_CREATED",
        target: license.publicId,
        metadata: { ownerId: owner.id, product: payload.product },
        ipHash: getClientIpHash(request)
      }
    });

    return NextResponse.json({ license: sanitizeLicenseForApi(license), rawKey }, { status: 201 });
  } catch (error) {
    return validationError(error);
  }
}
