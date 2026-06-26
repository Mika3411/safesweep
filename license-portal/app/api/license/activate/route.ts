import { NextRequest, NextResponse } from "next/server";
import { Prisma } from "@prisma/client";
import { prisma } from "@/lib/db";
import { jsonError, validationError } from "@/lib/http";
import {
  activateLicenseForDevice,
  checkLicenseEndpointRateLimit,
  checkLicensePayloadRateLimit,
  getLicenseEndpointMeta,
  licenseDeviceRequestSchema
} from "@/lib/license-api";

export async function POST(request: NextRequest) {
  const rate = await checkLicenseEndpointRateLimit(request, "activate");

  if (!rate.allowed) {
    return jsonError(
      rate.unavailable ? "Rate limit indisponible." : "Trop d'activations. Reessayez plus tard.",
      rate.unavailable ? 503 : 429
    );
  }

  try {
    const payload = licenseDeviceRequestSchema.parse(await request.json());
    const payloadRate = await checkLicensePayloadRateLimit(payload, "activate");

    if (!payloadRate.allowed) {
      return jsonError(
        payloadRate.unavailable ? "Rate limit indisponible." : "Trop d'activations. Reessayez plus tard.",
        payloadRate.unavailable ? 503 : 429
      );
    }

    const meta = getLicenseEndpointMeta(request);
    const result = await prisma.$transaction(
      (tx) => activateLicenseForDevice(tx, payload, meta),
      { isolationLevel: Prisma.TransactionIsolationLevel.Serializable }
    );

    return NextResponse.json(result.body, { status: result.statusCode });
  } catch (error) {
    return validationError(error);
  }
}
