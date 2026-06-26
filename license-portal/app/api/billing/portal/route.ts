import { NextRequest, NextResponse } from "next/server";
import { requireApiUser } from "@/lib/auth";
import { getAppUrl } from "@/lib/env";
import { jsonError, requireSameOrigin } from "@/lib/http";
import { getStripe } from "@/lib/stripe";
import { ensureStripeCustomerForUser } from "@/lib/stripe-billing";

export async function POST(request: NextRequest) {
  const csrfError = requireSameOrigin(request);

  if (csrfError) {
    return csrfError;
  }

  const user = await requireApiUser();

  if (!user) {
    return jsonError("Non authentifie.", 401);
  }

  const stripe = getStripe();
  const stripeCustomerId = await ensureStripeCustomerForUser(user);

  const portalSession = await stripe.billingPortal.sessions.create({
    customer: stripeCustomerId,
    return_url: `${getAppUrl()}/account`
  });

  return NextResponse.json({ url: portalSession.url });
}
