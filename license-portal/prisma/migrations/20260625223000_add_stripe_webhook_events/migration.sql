CREATE TYPE "StripeWebhookEventStatus" AS ENUM ('PROCESSING', 'PROCESSED', 'FAILED');

CREATE TABLE "stripe_webhook_events" (
  "id" UUID NOT NULL DEFAULT gen_random_uuid(),
  "eventId" TEXT NOT NULL,
  "type" TEXT NOT NULL,
  "status" "StripeWebhookEventStatus" NOT NULL DEFAULT 'PROCESSING',
  "error" TEXT,
  "receivedCount" INTEGER NOT NULL DEFAULT 1,
  "lastReceivedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "processedAt" TIMESTAMP(3),
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,

  CONSTRAINT "stripe_webhook_events_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "stripe_webhook_events_eventId_key" ON "stripe_webhook_events"("eventId");
CREATE INDEX "stripe_webhook_events_lastReceivedAt_idx" ON "stripe_webhook_events"("lastReceivedAt");
CREATE INDEX "stripe_webhook_events_status_lastReceivedAt_idx" ON "stripe_webhook_events"("status", "lastReceivedAt");
