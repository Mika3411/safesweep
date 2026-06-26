import Stripe from "stripe";
import { requireEnv } from "@/lib/env";

let stripe: Stripe | null = null;

export function getStripe() {
  if (!stripe) {
    stripe = new Stripe(requireEnv("STRIPE_SECRET_KEY"), {
      apiVersion: "2026-02-25.clover" as Stripe.LatestApiVersion,
      typescript: true
    });
  }

  return stripe;
}
