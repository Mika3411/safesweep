import { NextRequest, NextResponse } from "next/server";
import Stripe from "stripe";
import { requireEnv } from "@/lib/env";
import { getStripe } from "@/lib/stripe";
import { handleStripeWebhookEvent } from "@/lib/stripe-billing";
import { processStripeWebhookEvent } from "@/lib/stripe-webhook-events";

export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  const signature = request.headers.get("stripe-signature");

  if (!signature) {
    return NextResponse.json({ error: "Missing Stripe signature." }, { status: 400 });
  }

  const rawBody = await request.text();
  const stripe = getStripe();
  let event: Stripe.Event;

  try {
    event = stripe.webhooks.constructEvent(rawBody, signature, requireEnv("STRIPE_WEBHOOK_SECRET"));
  } catch (error) {
    const message = error instanceof Error ? error.message : "Invalid webhook signature.";
    return NextResponse.json({ error: message }, { status: 400 });
  }

  try {
    const result = await processStripeWebhookEvent(event, handleStripeWebhookEvent);

    return NextResponse.json({ received: true, duplicate: result.duplicate });
  } catch {
    return NextResponse.json({ error: "Stripe webhook processing failed." }, { status: 500 });
  }
}
