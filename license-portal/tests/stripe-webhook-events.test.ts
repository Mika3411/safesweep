import Stripe from "stripe";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  stripeWebhookEventCreate: vi.fn(),
  stripeWebhookEventUpdate: vi.fn()
}));

vi.mock("@/lib/db", () => ({
  prisma: {
    stripeWebhookEvent: {
      create: mocks.stripeWebhookEventCreate,
      update: mocks.stripeWebhookEventUpdate
    }
  }
}));

import { processStripeWebhookEvent } from "@/lib/stripe-webhook-events";

function stripeEvent(id = "evt_123") {
  return {
    id,
    type: "invoice.payment_succeeded",
    data: { object: { id: "in_123" } }
  } as unknown as Stripe.Event;
}

describe("Stripe webhook event monitoring", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("stores a received event and marks it processed after the handler succeeds", async () => {
    const handler = vi.fn(async () => undefined);
    mocks.stripeWebhookEventCreate.mockResolvedValue({});
    mocks.stripeWebhookEventUpdate.mockResolvedValue({});

    const result = await processStripeWebhookEvent(stripeEvent(), handler);

    expect(result).toEqual({
      processed: true,
      duplicate: false,
      status: "PROCESSED"
    });
    expect(mocks.stripeWebhookEventCreate).toHaveBeenCalledWith({
      data: expect.objectContaining({
        eventId: "evt_123",
        type: "invoice.payment_succeeded",
        status: "PROCESSING"
      })
    });
    expect(handler).toHaveBeenCalledOnce();
    expect(mocks.stripeWebhookEventUpdate).toHaveBeenLastCalledWith({
      where: { eventId: "evt_123" },
      data: expect.objectContaining({
        status: "PROCESSED",
        error: null,
        processedAt: expect.any(Date)
      })
    });
  });

  it("does not reprocess an already processed event id", async () => {
    const handler = vi.fn(async () => undefined);
    mocks.stripeWebhookEventCreate.mockRejectedValue({ code: "P2002" });
    mocks.stripeWebhookEventUpdate.mockResolvedValue({
      status: "PROCESSED"
    });

    const result = await processStripeWebhookEvent(stripeEvent(), handler);

    expect(result).toEqual({
      processed: false,
      duplicate: true,
      status: "PROCESSED"
    });
    expect(handler).not.toHaveBeenCalled();
    expect(mocks.stripeWebhookEventUpdate).toHaveBeenCalledTimes(1);
    expect(mocks.stripeWebhookEventUpdate).toHaveBeenCalledWith({
      where: { eventId: "evt_123" },
      data: expect.objectContaining({
        receivedCount: { increment: 1 },
        type: "invoice.payment_succeeded",
        lastReceivedAt: expect.any(Date)
      })
    });
  });

  it("marks a failed processing attempt without swallowing the error", async () => {
    const failure = new Error("invoice sync failed");
    const handler = vi.fn(async () => {
      throw failure;
    });
    mocks.stripeWebhookEventCreate.mockResolvedValue({});
    mocks.stripeWebhookEventUpdate.mockResolvedValue({});

    await expect(processStripeWebhookEvent(stripeEvent(), handler)).rejects.toThrow("invoice sync failed");

    expect(mocks.stripeWebhookEventUpdate).toHaveBeenLastCalledWith({
      where: { eventId: "evt_123" },
      data: {
        status: "FAILED",
        error: "invoice sync failed"
      }
    });
  });
});
