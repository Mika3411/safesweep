import { describe, expect, it } from "vitest";
import {
  generateLicenseKey,
  getLicenseDenyReason,
  hashFingerprint,
  hashLicenseKey,
  isLicenseKeyFormat,
  maskLicenseKey,
  normalizeLicenseKey
} from "@/lib/license";

describe("license helpers", () => {
  it("generates keys with the expected grouped format", () => {
    const key = generateLicenseKey();
    expect(isLicenseKeyFormat(key)).toBe(true);
    expect(key).toMatch(/^[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}$/);
  });

  it("normalizes and masks keys consistently", () => {
    expect(normalizeLicenseKey("abcd efgh ijkl mnop")).toBe("ABCD-EFGH-IJKL-MNOP");
    expect(maskLicenseKey("ABCD-EFGH-IJKL-MNOP")).toBe("ABCD-XXXX-XXXX-XXXX");
  });

  it("hashes license keys and fingerprints without storing raw secrets", () => {
    const keyHash = hashLicenseKey("ABCD-EFGH-IJKL-MNOP");
    const fingerprintHash = hashFingerprint("ACME-WS-01");

    expect(keyHash).toHaveLength(64);
    expect(fingerprintHash).toHaveLength(64);
    expect(keyHash).not.toContain("ABCD");
    expect(fingerprintHash).not.toContain("ACME");
  });

  it("returns a deny reason for unusable licenses", () => {
    expect(getLicenseDenyReason("REVOKED", new Date("2099-01-01"))).toBe("Licence revoquee.");
    expect(getLicenseDenyReason("SUSPENDED", new Date("2099-01-01"))).toBe("Licence suspendue.");
    expect(getLicenseDenyReason("ACTIVE", new Date("2020-01-01"), new Date("2026-01-01"))).toBe(
      "Licence expiree."
    );
    expect(getLicenseDenyReason("ACTIVE", new Date("2099-01-01"))).toBeNull();
  });
});
