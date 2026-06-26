import Stripe from "stripe";
import { prisma } from "@/lib/db";

type StripeWebhookEventStatus = "PROCESSING" | "PROCESSED" | "FAILED";

type StripeWebhookHandler = (event: Stripe.Event) => Promise<void>;

type ClaimedStripeWebhookEvent = {
  shouldProcess: boolean;
  status: StripeWebhookEventStatus;
};

export type StripeWebhookProcessResult = {
  processed: boolean;
  duplicate: boolean;
  status: StripeWebhookEventStatus;
};

const DUPLICATE_STATUSES = new Set<StripeWebhookEventStatus>(["PROCESSING", "PROCESSED"]);
const MAX_ERROR_LENGTH = 4000;

export async function processStripeWebhookEvent(
  event: Stripe.Event,
  handler: StripeWebhookHandler
): Promise<StripeWebhookProcessResult> {
  const claim = await claimStripeWebhookEvent(event);

  if (!claim.shouldProcess) {
    return {
      processed: false,
      duplicate: true,
      status: claim.status
    };
  }

  try {
    await handler(event);
    await prisma.stripeWebhookEvent.update({
      where: { eventId: event.id },
      data: {
        status: "PROCESSED",
        error: null,
        processedAt: new Date()
      }
    });

    return {
      processed: true,
      duplicate: false,
      status: "PROCESSED"
    };
  } catch (error) {
    await prisma.stripeWebhookEvent.update({
      where: { eventId: event.id },
      data: {
        status: "FAILED",
        error: formatWebhookError(error)
      }
    });

    throw error;
  }
}

async function claimStripeWebhookEvent(event: Stripe.Event): Promise<ClaimedStripeWebhookEvent> {
  const now = new Date();

  try {
    await prisma.stripeWebhookEvent.create({
      data: {
        eventId: event.id,
        type: event.type,
        status: "PROCESSING",
        lastReceivedAt: now
      }
    });

    return { shouldProcess: true, status: "PROCESSING" };
  } catch (error) {
    if (!isUniqueConstraintError(error)) {
      throw error;
    }
  }

  const existing = await prisma.stripeWebhookEvent.update({
    where: { eventId: event.id },
    data: {
      type: event.type,
      receivedCount: { increment: 1 },
      lastReceivedAt: now
    }
  });

  const status = existing.status as StripeWebhookEventStatus;

  if (DUPLICATE_STATUSES.has(status)) {
    return { shouldProcess: false, status };
  }

  await prisma.stripeWebhookEvent.update({
    where: { eventId: event.id },
    data: {
      status: "PROCESSING",
      error: null,
      lastReceivedAt: now
    }
  });

  return { shouldProcess: true, status: "PROCESSING" };
}

function isUniqueConstraintError(error: unknown) {
  return Boolean(error && typeof error === "object" && "code" in error && error.code === "P2002");
}

function formatWebhookError(error: unknown) {
  const message = error instanceof Error ? error.message : "Unknown Stripe webhook processing error";

  return message.slice(0, MAX_ERROR_LENGTH);
}
