import Stripe from "stripe";
import { describe, expect, it } from "vitest";
import {
  buildCheckoutMetadata,
  getStripeObjectId,
  getSubscriptionPeriodEnd,
  mapStripeSubscriptionStatus,
  normalizeProductCode,
  normalizePurchaseMetadata,
  shouldCreateLicenseAfterPayment
} from "@/lib/stripe-billing";

describe("Stripe billing helpers", () => {
  it("serializes checkout metadata for Stripe", () => {
    expect(
      buildCheckoutMetadata({
        checkoutType: "purchase",
        userId: "user-1",
        product: "ENDPOINT",
        maxActivations: 3,
        seatCount: 3
      })
    ).toEqual({
      checkoutType: "purchase",
      userId: "user-1",
      product: "ENDPOINT",
      maxActivations: "3",
      seatCount: "3"
    });
  });

  it("normalizes purchase metadata with conservative defaults", () => {
    expect(normalizeProductCode("SERVER")).toBe("SERVER");
    expect(normalizeProductCode("UNKNOWN")).toBe("ENDPOINT");
    expect(normalizePurchaseMetadata({ product: "SERVER", maxActivations: "0", seatCount: "999" })).toEqual({
      product: "SERVER",
      maxActivations: 1,
      seatCount: 500
    });
    expect(normalizePurchaseMetadata({ product: "MOBILE", maxActivations: "abc" })).toEqual({
      product: "MOBILE",
      maxActivations: 3,
      seatCount: 3
    });
  });

  it("creates licenses only for paid purchase subscriptions", () => {
    expect(shouldCreateLicenseAfterPayment({ checkoutType: "purchase", userId: "user-1" })).toBe(true);
    expect(
      shouldCreateLicenseAfterPayment({ checkoutType: "renew", userId: "user-1", licenseId: "license-1" })
    ).toBe(false);
    expect(shouldCreateLicenseAfterPayment({ checkoutType: "purchase" })).toBe(false);
  });

  it("maps Stripe subscription statuses to license statuses", () => {
    expect(mapStripeSubscriptionStatus("active")).toBe("ACTIVE");
    expect(mapStripeSubscriptionStatus("trialing")).toBe("ACTIVE");
    expect(mapStripeSubscriptionStatus("past_due")).toBe("SUSPENDED");
    expect(mapStripeSubscriptionStatus("canceled")).toBe("SUSPENDED");
  });

  it("extracts ids and subscription period endings from Stripe objects", () => {
    expect(getStripeObjectId("cus_123")).toBe("cus_123");
    expect(getStripeObjectId({ id: "sub_123" })).toBe("sub_123");
    expect(getStripeObjectId(null)).toBeUndefined();

    expect(
      getSubscriptionPeriodEnd({
        current_period_end: 1813881600
      } as unknown as Stripe.Subscription)?.toISOString()
    ).toBe("2027-06-25T00:00:00.000Z");

    expect(
      getSubscriptionPeriodEnd({
        items: { data: [{ current_period_end: 1813881600 }] }
      } as unknown as Stripe.Subscription)?.toISOString()
    ).toBe("2027-06-25T00:00:00.000Z");
  });
});
