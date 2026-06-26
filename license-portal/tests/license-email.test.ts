import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { buildLicenseKeyEmail, sendLicenseKeyEmail } from "@/lib/license-email";

const originalAppUrl = process.env.APP_URL;
const originalResendApiKey = process.env.RESEND_API_KEY;
const originalEmailFrom = process.env.EMAIL_FROM;
const originalEmailReplyTo = process.env.EMAIL_REPLY_TO;
const originalResendApiUrl = process.env.RESEND_API_URL;

function restoreEnv(name: string, value: string | undefined) {
  if (value === undefined) {
    delete process.env[name];
  } else {
    process.env[name] = value;
  }
}

const emailInput = {
  to: "client@safesweep.test",
  customerName: "Client SafeSweep",
  publicId: "SWP-ACME-0001",
  product: "SERVER",
  expiresAt: new Date("2027-06-25T00:00:00.000Z"),
  maxActivations: 1,
  seatCount: 1,
  licenseKey: "ABCD-EFGH-2345-MNPQ"
};

describe("license key email", () => {
  beforeEach(() => {
    process.env.APP_URL = "https://portal.example";
    process.env.RESEND_API_KEY = "re_test";
    process.env.EMAIL_FROM = "SafeSweep <licences@example.com>";
    process.env.EMAIL_REPLY_TO = "support@example.com";
    process.env.RESEND_API_URL = "https://resend.test/emails";
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    restoreEnv("APP_URL", originalAppUrl);
    restoreEnv("RESEND_API_KEY", originalResendApiKey);
    restoreEnv("EMAIL_FROM", originalEmailFrom);
    restoreEnv("EMAIL_REPLY_TO", originalEmailReplyTo);
    restoreEnv("RESEND_API_URL", originalResendApiUrl);
  });

  it("renders the raw key and license details", () => {
    const email = buildLicenseKeyEmail(emailInput);

    expect(email.subject).toBe("Votre cle de licence SafeSweep Server");
    expect(email.text).toContain("ABCD-EFGH-2345-MNPQ");
    expect(email.text).toContain("SafeSweep Server");
    expect(email.text).toContain("25 juin 2027");
    expect(email.text).toContain("Activations : 1");
    expect(email.html).toContain("ABCD-EFGH-2345-MNPQ");
  });

  it("sends the email through Resend", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ id: "email_123" }))
    );

    await expect(sendLicenseKeyEmail(emailInput)).resolves.toEqual({
      provider: "resend",
      messageId: "email_123"
    });

    expect(fetch).toHaveBeenCalledWith(
      "https://resend.test/emails",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          Authorization: "Bearer re_test",
          "Content-Type": "application/json"
        })
      })
    );
  });

  it("raises a descriptive error when Resend rejects the request", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ message: "Invalid sender" }, { status: 400 }))
    );

    await expect(sendLicenseKeyEmail(emailInput)).rejects.toThrow("Invalid sender");
  });
});
