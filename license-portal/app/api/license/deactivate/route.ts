import { NextRequest, NextResponse } from "next/server";
import { Prisma } from "@prisma/client";
import { prisma } from "@/lib/db";
import { jsonError, validationError } from "@/lib/http";
import {
  checkLicenseEndpointRateLimit,
  checkLicensePayloadRateLimit,
  deactivateLicenseForDevice,
  getLicenseEndpointMeta,
  licenseDeviceRequestSchema
} from "@/lib/license-api";

export async function POST(request: NextRequest) {
  const rate = await checkLicenseEndpointRateLimit(request, "deactivate");

  if (!rate.allowed) {
    return jsonError(
      rate.unavailable ? "Rate limit indisponible." : "Trop de desactivations. Reessayez plus tard.",
      rate.unavailable ? 503 : 429
    );
  }

  try {
    const payload = licenseDeviceRequestSchema.parse(await request.json());
    const payloadRate = await checkLicensePayloadRateLimit(payload, "deactivate");

    if (!payloadRate.allowed) {
      return jsonError(
        payloadRate.unavailable ? "Rate limit indisponible." : "Trop de desactivations. Reessayez plus tard.",
        payloadRate.unavailable ? 503 : 429
      );
    }

    const meta = getLicenseEndpointMeta(request);
    const result = await prisma.$transaction(
      (tx) => deactivateLicenseForDevice(tx, payload, meta),
      { isolationLevel: Prisma.TransactionIsolationLevel.Serializable }
    );

    return NextResponse.json(result.body, { status: result.statusCode });
  } catch (error) {
    return validationError(error);
  }
}
