import crypto from "node:crypto";
import { NextRequest } from "next/server";
import { Prisma } from "@prisma/client";
import { z } from "zod";
import { getClientIp } from "@/lib/http";
import {
  getLicenseDenyReason,
  hashFingerprint,
  hashIp,
  hashLicenseKey,
  isLicenseKeyFormat,
  normalizeLicenseKey
} from "@/lib/license";
import { checkRateLimit } from "@/lib/rate-limit";

type Transaction = Prisma.TransactionClient;

const SOFTWARE_CLIENT_SECRET_HEADER = "x-safesweep-client-secret";

export const licenseDeviceRequestSchema = z.object({
  licenseKey: z.string().min(19).max(64),
  deviceId: z.string().min(3).max(160),
  deviceName: z.string().min(2).max(120),
  platform: z.string().max(80).optional()
}).strict();

export type LicenseDeviceRequest = z.infer<typeof licenseDeviceRequestSchema>;

export type LicenseEndpointMeta = {
  ip: string;
  ipHash: string;
  userAgent?: string;
};

export type LicenseEndpointResult = {
  statusCode: number;
  body: Record<string, unknown>;
};

export const customerLicenseForApiSelect = Prisma.validator<Prisma.LicenseSelect>()({
  id: true,
  publicId: true,
  keyPrefix: true,
  encryptedLicenseKey: true,
  licenseKeyRevealedAt: true,
  product: true,
  status: true,
  expiresAt: true,
  deviceLimit: true,
  seatCount: true,
  subscriptionId: true,
  devices: {
    orderBy: { activatedAt: "desc" },
    select: {
      id: true,
      name: true,
      platform: true,
      activatedAt: true,
      deactivatedAt: true,
      lastSeenAt: true
    }
  },
  invoices: {
    orderBy: { createdAt: "desc" },
    select: {
      id: true,
      number: true,
      amountCents: true,
      currency: true,
      status: true,
      paidAt: true,
      dueAt: true,
      createdAt: true,
      hostedInvoiceUrl: true,
      invoicePdfUrl: true
    }
  },
  createdAt: true,
  updatedAt: true
});

type LicenseWithDevices = Prisma.LicenseGetPayload<{
  select: typeof customerLicenseForApiSelect;
}> & {
  owner?: {
    id: string;
    name: string;
    email: string;
    company?: string | null;
  } | null;
};

export function getLicenseEndpointMeta(request: NextRequest): LicenseEndpointMeta {
  const ip = getClientIp(request);

  return {
    ip,
    ipHash: hashIp(ip),
    userAgent: request.headers.get("user-agent") ?? undefined
  };
}

export function checkSoftwareClientSecret(request: NextRequest) {
  const clientSecret = process.env.LICENSE_API_SECRET ?? "";
  const providedSecret = request.headers.get(SOFTWARE_CLIENT_SECRET_HEADER) ?? "";

  if (!clientSecret.trim() || !providedSecret) {
    return false;
  }

  const clientSecretDigest = crypto.createHash("sha256").update(clientSecret).digest();
  const providedSecretDigest = crypto.createHash("sha256").update(providedSecret).digest();

  return crypto.timingSafeEqual(clientSecretDigest, providedSecretDigest);
}

export async function checkLicenseEndpointRateLimit(
  request: NextRequest,
  action: "validate" | "activate" | "deactivate"
) {
  const ip = getClientIp(request);

  return checkRateLimit({
    key: `license:${action}:${ip}`,
    limit: action === "validate" ? 90 : 30,
    windowMs: 60 * 1000
  });
}

export async function checkLicensePayloadRateLimit(
  payload: LicenseDeviceRequest,
  action: "validate" | "activate" | "deactivate"
) {
  const licenseHash = hashLicenseKey(payload.licenseKey).slice(0, 24);
  const fingerprintHash = hashFingerprint(payload.deviceId).slice(0, 24);
  const licenseLimit = await checkRateLimit({
    key: `license:${action}:key:${licenseHash}`,
    limit: action === "validate" ? 120 : 40,
    windowMs: 60 * 1000
  });

  if (!licenseLimit.allowed) {
    return licenseLimit;
  }

  return checkRateLimit({
    key: `license:${action}:device:${licenseHash}:${fingerprintHash}`,
    limit: action === "validate" ? 60 : 15,
    windowMs: 60 * 1000
  });
}

export function formatApiDate(date: Date) {
  return date.toISOString().slice(0, 10);
}

export function getRemainingActivations(maxActivations: number, activeActivations: number) {
  return Math.max(maxActivations - activeActivations, 0);
}

export function sanitizeLicenseForApi(license: LicenseWithDevices) {
  const activeDevices = license.devices.filter((device) => !device.deactivatedAt);

  return {
    id: license.id,
    publicId: license.publicId,
    keyPrefix: license.keyPrefix,
    licenseKeyAvailable: Boolean(license.encryptedLicenseKey && !license.licenseKeyRevealedAt),
    licenseKeyRevealedAt: license.licenseKeyRevealedAt ? license.licenseKeyRevealedAt.toISOString() : null,
    owner: license.owner,
    product: license.product,
    status: license.status.toLowerCase(),
    expiresAt: formatApiDate(license.expiresAt),
    deviceLimit: license.deviceLimit,
    seatCount: license.seatCount,
    maxActivations: license.deviceLimit,
    activeActivations: activeDevices.length,
    remainingActivations: getRemainingActivations(license.deviceLimit, activeDevices.length),
    seats: license.seatCount,
    subscriptionId: license.subscriptionId,
    devices: license.devices.map((device) => ({
      id: device.id,
      name: device.name,
      platform: device.platform,
      activatedAt: device.activatedAt.toISOString(),
      deactivatedAt: device.deactivatedAt ? device.deactivatedAt.toISOString() : null,
      lastSeenAt: device.lastSeenAt ? device.lastSeenAt.toISOString() : null
    })),
    invoices: license.invoices.map((invoice) => ({
      id: invoice.id,
      number: invoice.number,
      amountCents: invoice.amountCents,
      currency: invoice.currency,
      status: invoice.status,
      paidAt: invoice.paidAt ? invoice.paidAt.toISOString() : null,
      dueAt: invoice.dueAt ? invoice.dueAt.toISOString() : null,
      createdAt: invoice.createdAt.toISOString(),
      hostedInvoiceUrl: invoice.hostedInvoiceUrl,
      invoicePdfUrl: invoice.invoicePdfUrl
    })),
    createdAt: license.createdAt.toISOString(),
    updatedAt: license.updatedAt.toISOString()
  };
}

export async function validateLicenseForDevice(
  tx: Transaction,
  payload: LicenseDeviceRequest,
  meta: LicenseEndpointMeta
): Promise<LicenseEndpointResult> {
  const normalizedKey = normalizeLicenseKey(payload.licenseKey);
  const fingerprintHash = hashFingerprint(payload.deviceId);

  if (!isLicenseKeyFormat(normalizedKey)) {
    await logLicenseValidation(tx, {
      fingerprintHash,
      action: "NOT_FOUND",
      result: "DENIED",
      reason: "Format de cle invalide",
      meta
    });

    return {
      statusCode: 400,
      body: {
        valid: false,
        status: "invalid",
        reason: "Format de licence invalide."
      }
    };
  }

  const license = await tx.license.findUnique({
    where: { keyHash: hashLicenseKey(normalizedKey) },
    include: { devices: true }
  });

  if (!license) {
    await logLicenseValidation(tx, {
      fingerprintHash,
      action: "NOT_FOUND",
      result: "DENIED",
      reason: "Licence introuvable",
      meta
    });

    return {
      statusCode: 404,
      body: {
        valid: false,
        status: "not_found",
        reason: "Licence introuvable."
      }
    };
  }

  const now = new Date();
  const denyReason = getLicenseDenyReason(license.status, license.expiresAt, now);
  const activeDevices = license.devices.filter((device) => !device.deactivatedAt);
  const knownDevice = license.devices.find((device) => device.fingerprintHash === fingerprintHash);

  if (denyReason) {
    const action =
      license.status === "REVOKED"
        ? "REVOKED_DENIED"
        : license.status === "SUSPENDED"
          ? "SUSPENDED_DENIED"
          : "EXPIRED_DENIED";

    if (license.status === "ACTIVE" && license.expiresAt.getTime() < now.getTime()) {
      await tx.license.update({ where: { id: license.id }, data: { status: "EXPIRED" } });
    }

    await logLicenseValidation(tx, {
      licenseId: license.id,
      deviceId: knownDevice?.id,
      fingerprintHash,
      action,
      result: "DENIED",
      reason: denyReason,
      meta
    });

    return {
      statusCode: 403,
      body: {
        valid: false,
        status: license.expiresAt.getTime() < now.getTime() ? "expired" : license.status.toLowerCase(),
        expiresAt: formatApiDate(license.expiresAt),
        reason: denyReason,
        remainingActivations: getRemainingActivations(license.deviceLimit, activeDevices.length)
      }
    };
  }

  const deviceIsActive = Boolean(knownDevice && !knownDevice.deactivatedAt);
  const remainingActivations = getRemainingActivations(license.deviceLimit, activeDevices.length);

  if (!deviceIsActive && remainingActivations <= 0) {
    await logLicenseValidation(tx, {
      licenseId: license.id,
      deviceId: knownDevice?.id,
      fingerprintHash,
      action: "DEVICE_LIMIT_REACHED",
      result: "DENIED",
      reason: "Nombre maximal d'activations atteint",
      meta
    });

    return {
      statusCode: 403,
      body: {
        valid: false,
        status: license.status.toLowerCase(),
        expiresAt: formatApiDate(license.expiresAt),
        reason: "Nombre maximal d'activations atteint.",
        remainingActivations: 0
      }
    };
  }

  await logLicenseValidation(tx, {
    licenseId: license.id,
    deviceId: knownDevice?.id,
    fingerprintHash,
    action: "VALIDATED",
    result: "ALLOWED",
    reason: deviceIsActive ? "Appareil deja active" : "Activation disponible",
    meta
  });

  return {
    statusCode: 200,
    body: {
      valid: true,
      status: license.status.toLowerCase(),
      expiresAt: formatApiDate(license.expiresAt),
      remainingActivations,
      deviceAuthorized: deviceIsActive,
      requiresActivation: !deviceIsActive
    }
  };
}

export async function activateLicenseForDevice(
  tx: Transaction,
  payload: LicenseDeviceRequest,
  meta: LicenseEndpointMeta
): Promise<LicenseEndpointResult> {
  const validation = await validateLicenseForDevice(tx, payload, meta);

  if (validation.statusCode !== 200) {
    return validation;
  }

  const normalizedKey = normalizeLicenseKey(payload.licenseKey);
  const fingerprintHash = hashFingerprint(payload.deviceId);
  const license = await tx.license.findUnique({
    where: { keyHash: hashLicenseKey(normalizedKey) },
    include: { devices: true }
  });

  if (!license) {
    return validation;
  }

  const now = new Date();
  const activeDevices = license.devices.filter((device) => !device.deactivatedAt);
  const knownDevice = license.devices.find((device) => device.fingerprintHash === fingerprintHash);
  let deviceId = knownDevice?.id;
  let activeCountAfter = activeDevices.length;
  let action: "DEVICE_ACTIVATED" | "DEVICE_REACTIVATED" | "VALIDATED" = "VALIDATED";

  if (!knownDevice) {
    const device = await tx.device.create({
      data: {
        licenseId: license.id,
        fingerprintHash,
        name: payload.deviceName,
        platform: payload.platform,
        lastSeenAt: now
      }
    });

    deviceId = device.id;
    activeCountAfter += 1;
    action = "DEVICE_ACTIVATED";
  } else if (knownDevice.deactivatedAt) {
    await tx.device.update({
      where: { id: knownDevice.id },
      data: {
        deactivatedAt: null,
        lastSeenAt: now,
        name: payload.deviceName,
        platform: payload.platform
      }
    });

    activeCountAfter += 1;
    action = "DEVICE_REACTIVATED";
  } else {
    await tx.device.update({
      where: { id: knownDevice.id },
      data: {
        lastSeenAt: now,
        name: payload.deviceName,
        platform: payload.platform
      }
    });
  }

  await logLicenseValidation(tx, {
    licenseId: license.id,
    deviceId,
    fingerprintHash,
    action,
    result: "ALLOWED",
    reason: action === "VALIDATED" ? "Activation deja existante" : "Activation enregistree",
    meta
  });

  return {
    statusCode: 200,
    body: {
      valid: true,
      activated: true,
      status: license.status.toLowerCase(),
      expiresAt: formatApiDate(license.expiresAt),
      remainingActivations: getRemainingActivations(license.deviceLimit, activeCountAfter)
    }
  };
}

export async function deactivateLicenseForDevice(
  tx: Transaction,
  payload: LicenseDeviceRequest,
  meta: LicenseEndpointMeta
): Promise<LicenseEndpointResult> {
  const normalizedKey = normalizeLicenseKey(payload.licenseKey);
  const fingerprintHash = hashFingerprint(payload.deviceId);

  if (!isLicenseKeyFormat(normalizedKey)) {
    await logLicenseValidation(tx, {
      fingerprintHash,
      action: "NOT_FOUND",
      result: "DENIED",
      reason: "Format de cle invalide",
      meta
    });

    return {
      statusCode: 400,
      body: { valid: false, deactivated: false, reason: "Format de licence invalide." }
    };
  }

  const license = await tx.license.findUnique({
    where: { keyHash: hashLicenseKey(normalizedKey) },
    include: { devices: true }
  });

  if (!license) {
    await logLicenseValidation(tx, {
      fingerprintHash,
      action: "NOT_FOUND",
      result: "DENIED",
      reason: "Licence introuvable",
      meta
    });

    return {
      statusCode: 404,
      body: { valid: false, deactivated: false, reason: "Licence introuvable." }
    };
  }

  const device = license.devices.find((item) => item.fingerprintHash === fingerprintHash);

  if (!device || device.deactivatedAt) {
    await logLicenseValidation(tx, {
      licenseId: license.id,
      deviceId: device?.id,
      fingerprintHash,
      action: "VALIDATED",
      result: "DENIED",
      reason: "Appareil non actif",
      meta
    });

    return {
      statusCode: 404,
      body: { valid: false, deactivated: false, reason: "Appareil non actif pour cette licence." }
    };
  }

  await tx.device.update({
    where: { id: device.id },
    data: { deactivatedAt: new Date(), lastSeenAt: new Date() }
  });

  await logLicenseValidation(tx, {
    licenseId: license.id,
    deviceId: device.id,
    fingerprintHash,
    action: "VALIDATED",
    result: "ALLOWED",
    reason: "Appareil desactive",
    meta
  });

  const activeCountAfter = license.devices.filter(
    (item) => !item.deactivatedAt && item.id !== device.id
  ).length;

  return {
    statusCode: 200,
    body: {
      valid: true,
      deactivated: true,
      status: license.status.toLowerCase(),
      expiresAt: formatApiDate(license.expiresAt),
      remainingActivations: getRemainingActivations(license.deviceLimit, activeCountAfter)
    }
  };
}

async function logLicenseValidation(
  tx: Transaction,
  data: {
    licenseId?: string;
    deviceId?: string;
    fingerprintHash?: string;
    action:
      | "VALIDATED"
      | "DEVICE_ACTIVATED"
      | "DEVICE_REACTIVATED"
      | "DEVICE_LIMIT_REACHED"
      | "EXPIRED_DENIED"
      | "SUSPENDED_DENIED"
      | "REVOKED_DENIED"
      | "NOT_FOUND";
    result: "ALLOWED" | "DENIED";
    reason: string;
    meta: LicenseEndpointMeta;
  }
) {
  await tx.licenseValidation.create({
    data: {
      licenseId: data.licenseId,
      deviceId: data.deviceId,
      fingerprintHash: data.fingerprintHash,
      action: data.action,
      result: data.result,
      reason: data.reason,
      ipHash: data.meta.ipHash,
      userAgent: data.meta.userAgent
    }
  });
}
