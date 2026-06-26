import crypto from "node:crypto";
import { getLicenseKeyEncryptionSecret } from "@/lib/env";
import { normalizeLicenseKey } from "@/lib/license";

const ENVELOPE_VERSION = "v1";
const SALT_BYTES = 16;
const IV_BYTES = 12;
const KEY_BYTES = 32;

function deriveKey(salt: Buffer) {
  const secret = getLicenseKeyEncryptionSecret();

  if (secret.length < 32) {
    throw new Error("LICENSE_KEY_ENCRYPTION_SECRET must contain at least 32 characters.");
  }

  return crypto.scryptSync(secret, salt, KEY_BYTES);
}

export function encryptLicenseKey(licenseKey: string) {
  const salt = crypto.randomBytes(SALT_BYTES);
  const iv = crypto.randomBytes(IV_BYTES);
  const key = deriveKey(salt);
  const cipher = crypto.createCipheriv("aes-256-gcm", key, iv);
  const normalized = normalizeLicenseKey(licenseKey);
  const ciphertext = Buffer.concat([cipher.update(normalized, "utf8"), cipher.final()]);
  const tag = cipher.getAuthTag();

  return [ENVELOPE_VERSION, salt.toString("base64url"), iv.toString("base64url"), tag.toString("base64url"), ciphertext.toString("base64url")].join(".");
}

export function decryptLicenseKey(encryptedLicenseKey: string) {
  const [version, saltValue, ivValue, tagValue, ciphertextValue] = encryptedLicenseKey.split(".");

  if (version !== ENVELOPE_VERSION || !saltValue || !ivValue || !tagValue || !ciphertextValue) {
    throw new Error("Unsupported encrypted license key format.");
  }

  const salt = Buffer.from(saltValue, "base64url");
  const iv = Buffer.from(ivValue, "base64url");
  const tag = Buffer.from(tagValue, "base64url");
  const ciphertext = Buffer.from(ciphertextValue, "base64url");
  const decipher = crypto.createDecipheriv("aes-256-gcm", deriveKey(salt), iv);

  decipher.setAuthTag(tag);

  return Buffer.concat([decipher.update(ciphertext), decipher.final()]).toString("utf8");
}
