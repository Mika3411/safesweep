import crypto from "node:crypto";
import { getLicenseHashSecret } from "@/lib/env";

export type StoredLicenseStatus = "ACTIVE" | "EXPIRED" | "SUSPENDED" | "REVOKED";

export const LICENSE_KEY_PATTERN = /^[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}$/;
const LICENSE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";

export function normalizeLicenseKey(value: string) {
  return value.trim().toUpperCase().replace(/[^A-Z0-9]/g, "").replace(/(.{4})(?=.)/g, "$1-");
}

export function isLicenseKeyFormat(value: string) {
  return LICENSE_KEY_PATTERN.test(normalizeLicenseKey(value));
}

export function generateLicenseKey() {
  let raw = "";

  for (let index = 0; index < 16; index += 1) {
    raw += LICENSE_ALPHABET[crypto.randomInt(0, LICENSE_ALPHABET.length)];
  }

  return raw.match(/.{1,4}/g)?.join("-") ?? raw;
}

export function hashLicenseKey(licenseKey: string) {
  return crypto
    .createHmac("sha256", getLicenseHashSecret())
    .update(normalizeLicenseKey(licenseKey))
    .digest("hex");
}

export function hashFingerprint(value: string) {
  return crypto.createHash("sha256").update(value.trim().toLowerCase()).digest("hex");
}

export function hashIp(value: string) {
  return crypto.createHash("sha256").update(value.trim()).digest("hex");
}

export function maskLicenseKey(licenseKeyOrPrefix: string) {
  const normalized = normalizeLicenseKey(licenseKeyOrPrefix);
  const firstGroup = normalized.split("-")[0] || "XXXX";
  return `${firstGroup}-XXXX-XXXX-XXXX`;
}

export function getLicenseDenyReason(
  status: StoredLicenseStatus,
  expiresAt: Date,
  now = new Date()
) {
  if (status === "REVOKED") {
    return "Licence revoquee.";
  }

  if (status === "SUSPENDED") {
    return "Licence suspendue.";
  }

  if (status === "EXPIRED" || expiresAt.getTime() < now.getTime()) {
    return "Licence expiree.";
  }

  return null;
}

export function buildPublicLicenseId(company: string | null | undefined, sequence: number) {
  const prefix = (company ?? "CLIENT")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9]/g, "")
    .slice(0, 6)
    .toUpperCase()
    .padEnd(4, "X");

  return `SWP-${prefix}-${String(sequence).padStart(4, "0")}`;
}
