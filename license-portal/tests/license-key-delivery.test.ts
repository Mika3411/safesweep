import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { decryptLicenseKey, encryptLicenseKey } from "@/lib/license-key-delivery";

const originalSecret = process.env.LICENSE_KEY_ENCRYPTION_SECRET;

describe("license key delivery encryption", () => {
  beforeEach(() => {
    process.env.LICENSE_KEY_ENCRYPTION_SECRET = "test-license-key-encryption-secret-32";
  });

  afterEach(() => {
    if (originalSecret === undefined) {
      delete process.env.LICENSE_KEY_ENCRYPTION_SECRET;
    } else {
      process.env.LICENSE_KEY_ENCRYPTION_SECRET = originalSecret;
    }
  });

  it("encrypts and decrypts normalized license keys", () => {
    const encrypted = encryptLicenseKey("abcd-efgh-2345-mnpq");

    expect(encrypted).toMatch(/^v1\./);
    expect(encrypted).not.toContain("ABCD");
    expect(decryptLicenseKey(encrypted)).toBe("ABCD-EFGH-2345-MNPQ");
  });
});
