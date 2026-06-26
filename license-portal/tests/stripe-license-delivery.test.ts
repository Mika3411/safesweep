import Stripe from "stripe";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { decryptLicenseKey } from "@/lib/license-key-delivery";
import { hashLicenseKey, isLicenseKeyFormat } from "@/lib/license";

const mocks = vi.hoisted(() => ({
  stripeSubscriptionRetrieve: vi.fn(),
  userFindUnique: vi.fn(),
  licenseFindUnique: vi.fn(),
  licenseUpdate: vi.fn(),
  invoiceUpsert: vi.fn(),
  paymentFindUnique: vi.fn(),
  paymentUpsert: vi.fn(),
  auditLogCreate: vi.fn(),
  transaction: vi.fn(),
  txLicenseFindUnique: vi.fn(),
  txLicenseCount: vi.fn(),
  txLicenseCreate: vi.fn(),
  txLicenseValidationCreate: vi.fn(),
  txAuditLogCreate: vi.fn()
}));

vi.mock("@/lib/stripe", () => ({
  getStripe: () => ({
    subscriptions: {
      retrieve: mocks.stripeSubscriptionRetrieve
    }
  })
}));

vi.mock("@/lib/db", () => ({
  prisma: {
    user: {
      findUnique: mocks.userFindUnique
    },
    license: {
      findUnique: mocks.licenseFindUnique,
      update: mocks.licenseUpdate
    },
    invoice: {
      upsert: mocks.invoiceUpsert
    },
    payment: {
      findUnique: mocks.paymentFindUnique,
      upsert: mocks.paymentUpsert
    },
    auditLog: {
      create: mocks.auditLogCreate
    },
    $transaction: mocks.transaction
  }
}));

import { handleInvoicePaymentSucceeded } from "@/lib/stripe-billing";

const originalEncryptionSecret = process.env.LICENSE_KEY_ENCRYPTION_SECRET;
const originalHashSecret = process.env.LICENSE_HASH_SECRET;
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

describe("Stripe invoice license delivery", () => {
  beforeEach(() => {
    process.env.LICENSE_KEY_ENCRYPTION_SECRET = "test-license-key-encryption-secret-32";
    process.env.LICENSE_HASH_SECRET = "test-license-hash-secret-32";
    process.env.APP_URL = "https://portal.example";
    process.env.RESEND_API_KEY = "re_test";
    process.env.EMAIL_FROM = "SafeSweep <licences@example.com>";
    process.env.EMAIL_REPLY_TO = "support@example.com";
    delete process.env.RESEND_API_URL;
    vi.clearAllMocks();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ id: "email_123" }))
    );

    mocks.userFindUnique.mockResolvedValue({
      id: "user-id",
      email: "client@safesweep.test",
      name: "Client",
      company: "Acme",
      stripeCustomerId: null
    });
    mocks.licenseFindUnique.mockImplementation(async (args) =>
      args.where?.id === "license-id"
        ? {
            id: "license-id",
            publicId: "SWP-ACME-0001",
            ownerId: "user-id",
            subscriptionId: "sub_123"
          }
        : null
    );
    mocks.licenseUpdate.mockResolvedValue({});
    mocks.invoiceUpsert.mockResolvedValue({});
    mocks.paymentFindUnique.mockResolvedValue(null);
    mocks.paymentUpsert.mockResolvedValue({});
    mocks.auditLogCreate.mockResolvedValue({});
    mocks.txLicenseFindUnique.mockResolvedValue(null);
    mocks.txLicenseCount.mockResolvedValue(0);
    mocks.txLicenseCreate.mockImplementation(async ({ data }) => ({
      id: "license-id",
      publicId: data.publicId,
      ownerId: data.ownerId,
      subscriptionId: data.subscriptionId
    }));
    mocks.txLicenseValidationCreate.mockResolvedValue({});
    mocks.txAuditLogCreate.mockResolvedValue({});
    mocks.transaction.mockImplementation(async (callback) =>
      callback({
        license: {
          findUnique: mocks.txLicenseFindUnique,
          count: mocks.txLicenseCount,
          create: mocks.txLicenseCreate
        },
        licenseValidation: {
          create: mocks.txLicenseValidationCreate
        },
        auditLog: {
          create: mocks.txAuditLogCreate
        }
      })
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    restoreEnv("LICENSE_KEY_ENCRYPTION_SECRET", originalEncryptionSecret);
    restoreEnv("LICENSE_HASH_SECRET", originalHashSecret);
    restoreEnv("APP_URL", originalAppUrl);
    restoreEnv("RESEND_API_KEY", originalResendApiKey);
    restoreEnv("EMAIL_FROM", originalEmailFrom);
    restoreEnv("EMAIL_REPLY_TO", originalEmailReplyTo);
    restoreEnv("RESEND_API_URL", originalResendApiUrl);
  });

  function paidInvoice() {
    return {
      id: "in_123",
      status: "paid",
      paid: true,
      subscription: "sub_123",
      amount_paid: 9900,
      currency: "eur",
      metadata: {}
    } as unknown as Stripe.Invoice;
  }

  function paidSubscription() {
    return {
      id: "sub_123",
      status: "active",
      current_period_end: 1813881600,
      metadata: {
        checkoutType: "purchase",
        userId: "user-id",
        product: "ENDPOINT",
        maxActivations: "3",
        seatCount: "3"
      }
    } as unknown as Stripe.Subscription;
  }

  it("creates a paid Stripe license, sends the raw key by email, and stores only protected key material", async () => {
    mocks.stripeSubscriptionRetrieve.mockResolvedValue({
      id: "sub_123",
      status: "active",
      current_period_end: 1813881600,
      metadata: {
        checkoutType: "purchase",
        userId: "user-id",
        product: "ENDPOINT",
        maxActivations: "3",
        seatCount: "3"
      }
    } as unknown as Stripe.Subscription);

    await handleInvoicePaymentSucceeded(paidInvoice());

    const createCall = mocks.txLicenseCreate.mock.calls[0]?.[0];

    expect(createCall.data.keyHash).toEqual(expect.any(String));
    expect(createCall.data.keyPrefix).toEqual(expect.any(String));
    expect(createCall.data.encryptedLicenseKey).toMatch(/^v1\./);
    expect(createCall.data).not.toHaveProperty("rawLicenseKey");
    expect(createCall.data).not.toHaveProperty("licenseKey");

    const decrypted = decryptLicenseKey(createCall.data.encryptedLicenseKey);
    const emailRequest = vi.mocked(fetch).mock.calls[0];
    const emailBody = JSON.parse(String(emailRequest[1]?.body)) as {
      to: string[];
      subject: string;
      text: string;
      html: string;
    };

    expect(isLicenseKeyFormat(decrypted)).toBe(true);
    expect(hashLicenseKey(decrypted)).toBe(createCall.data.keyHash);
    expect(emailRequest[0]).toBe("https://api.resend.com/emails");
    expect(emailBody.to).toEqual(["client@safesweep.test"]);
    expect(emailBody.text).toContain(decrypted);
    expect(emailBody.text).toContain("SafeSweep Endpoint");
    expect(emailBody.text).toContain("25 juin 2027");
    expect(emailBody.text).toContain("Activations : 3");
    expect(emailBody.html).toContain(decrypted);
    expect(mocks.txAuditLogCreate).toHaveBeenCalledWith({
      data: expect.objectContaining({
        action: "LICENSE_CREATED_FROM_STRIPE",
        metadata: expect.objectContaining({ rawKeyDelivery: "encrypted_one_time" })
      })
    });
    expect(mocks.txAuditLogCreate).toHaveBeenCalledWith({
      data: expect.objectContaining({
        action: "LICENSE_KEY_STAGED_FOR_REVEAL",
        metadata: expect.objectContaining({ delivery: "encrypted_one_time" })
      })
    });
    expect(mocks.auditLogCreate).toHaveBeenCalledWith({
      data: expect.objectContaining({
        action: "LICENSE_KEY_EMAIL_SENT",
        target: expect.any(String),
        metadata: expect.objectContaining({
          provider: "resend",
          messageId: "email_123",
          keyPrefix: decrypted.split("-")[0]
        })
      })
    });
  });

  it("logs email failures without breaking Stripe webhook processing", async () => {
    mocks.stripeSubscriptionRetrieve.mockResolvedValue(paidSubscription());
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ message: "Resend unavailable" }, { status: 503 }))
    );

    await expect(handleInvoicePaymentSucceeded(paidInvoice())).resolves.toBeUndefined();

    expect(mocks.invoiceUpsert).toHaveBeenCalled();
    expect(mocks.paymentUpsert).toHaveBeenCalled();
    expect(mocks.auditLogCreate).toHaveBeenCalledWith({
      data: expect.objectContaining({
        action: "LICENSE_KEY_EMAIL_FAILED",
        metadata: expect.objectContaining({
          error: "Resend unavailable"
        })
      })
    });
  });
});
