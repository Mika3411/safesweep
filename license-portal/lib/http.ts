import { NextRequest, NextResponse } from "next/server";
import { ZodError } from "zod";
import { getAppUrl } from "@/lib/env";
import { hashIp } from "@/lib/license";

export function jsonError(message: string, status = 400, details?: unknown) {
  return NextResponse.json({ error: message, details }, { status });
}

export function validationError(error: unknown) {
  if (error instanceof ZodError) {
    return jsonError("Requete invalide.", 422, error.flatten());
  }

  return jsonError("Requete invalide.", 422);
}

function parseOrigin(value: string | null | undefined) {
  if (!value) {
    return null;
  }

  try {
    return new URL(value).origin;
  } catch {
    return null;
  }
}

function normalizeHost(value: string | null | undefined) {
  const host = value?.split(",")[0]?.trim().toLowerCase().replace(/\.$/, "");

  if (!host || host.includes("/") || host.includes("@")) {
    return null;
  }

  try {
    return new URL(`http://${host}`).host;
  } catch {
    return null;
  }
}

function getCsrfTrustedOrigins() {
  return new Set(
    [getAppUrl(), ...(process.env.CSRF_TRUSTED_ORIGINS ?? "").split(",")]
      .map((origin) => parseOrigin(origin.trim()))
      .filter((origin): origin is string => Boolean(origin))
  );
}

function getCsrfTrustedHosts() {
  return new Set(
    [...getCsrfTrustedOrigins()]
      .map((origin) => normalizeHost(new URL(origin).host))
      .filter((host): host is string => Boolean(host))
  );
}

function getRequestHost(request: NextRequest) {
  return normalizeHost(request.headers.get("host")) ?? normalizeHost(request.nextUrl.host);
}

export function requireSameOrigin(request: NextRequest) {
  const origin = parseOrigin(request.headers.get("origin"));

  if (!origin || !getCsrfTrustedOrigins().has(origin)) {
    return jsonError("Origin non autorisee.", 403);
  }

  const host = getRequestHost(request);

  if (!host || !getCsrfTrustedHosts().has(host)) {
    return jsonError("Host non autorise.", 403);
  }

  return null;
}

function normalizeIp(value: string | null | undefined) {
  const ip = value?.trim().replace(/^\[|\]$/g, "");

  if (!ip) {
    return null;
  }

  return ip.startsWith("::ffff:") ? ip.slice(7) : ip;
}

function parseForwardedFor(value: string | null) {
  return (value ?? "")
    .split(",")
    .map(normalizeIp)
    .filter((ip): ip is string => Boolean(ip));
}

function ipv4ToNumber(ip: string) {
  const parts = ip.split(".");

  if (parts.length !== 4) {
    return null;
  }

  let value = 0;

  for (const part of parts) {
    const octet = Number(part);

    if (!Number.isInteger(octet) || octet < 0 || octet > 255) {
      return null;
    }

    value = (value << 8) + octet;
  }

  return value >>> 0;
}

function ipv4MatchesCidr(ip: string, cidr: string) {
  const [range, prefixValue] = cidr.split("/");
  const prefix = Number(prefixValue);
  const ipValue = ipv4ToNumber(ip);
  const rangeValue = ipv4ToNumber(range ?? "");

  if (ipValue === null || rangeValue === null || !Number.isInteger(prefix) || prefix < 0 || prefix > 32) {
    return false;
  }

  const mask = prefix === 0 ? 0 : (0xffffffff << (32 - prefix)) >>> 0;

  return (ipValue & mask) === (rangeValue & mask);
}

function getTrustedProxyRules() {
  return (process.env.TRUSTED_PROXY_IPS ?? "")
    .split(",")
    .map((rule) => rule.trim())
    .filter(Boolean);
}

function isTrustedProxy(ip: string | null) {
  if (!ip) {
    return false;
  }

  return getTrustedProxyRules().some((rule) => {
    if (rule.includes("/")) {
      return ipv4MatchesCidr(ip, rule);
    }

    return normalizeIp(rule) === ip;
  });
}

function getDirectIp(request: NextRequest) {
  return normalizeIp((request as NextRequest & { ip?: string }).ip);
}

export function getClientIp(request: NextRequest) {
  const directIp = getDirectIp(request);

  if (isTrustedProxy(directIp)) {
    const forwardedFor = parseForwardedFor(request.headers.get("x-forwarded-for"));
    const forwardedIp = forwardedFor.at(-1);

    if (forwardedIp) {
      return forwardedIp;
    }

    const realIp = normalizeIp(request.headers.get("x-real-ip"));

    if (realIp) {
      return realIp;
    }
  }

  return directIp ?? "unknown";
}

export function getClientIpHash(request: NextRequest) {
  return hashIp(getClientIp(request));
}
