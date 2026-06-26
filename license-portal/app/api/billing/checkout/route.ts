import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { requireApiUser } from "@/lib/auth";
import { prisma } from "@/lib/db";
import { getAppUrl } from "@/lib/env";
import { getClientIp, jsonError, requireSameOrigin, validationError } from "@/lib/http";
import { checkRateLimit } from "@/lib/rate-limit";
import { getStripe } from "@/lib/stripe";
import {
  buildCheckoutMetadata,
  ensureStripeCustomerForUser,
  getStripePriceIdForProduct,
  normalizeProductCode
} from "@/lib/stripe-billing";

const checkoutSchema = z.object({
  licenseId: z.string().uuid().optional(),
  product: z.enum(["ENDPOINT", "SERVER", "MOBILE"]).optional(),
  maxActivations: z.number().int().min(1).max(500).optional(),
  seatCount: z.number().int().min(1).max(500).optional()
});

export async function POST(request: NextRequest) {
  const csrfError = requireSameOrigin(request);

  if (csrfError) {
    return csrfError;
  }

  const user = await requireApiUser();

  if (!user) {
    return jsonError("Non authentifie.", 401);
  }

  const rateLimit = await checkRateLimit({
    key: `billing:checkout:${user.id}:${getClientIp(request)}`,
    limit: 12,
    windowMs: 60 * 1000
  });

  if (!rateLimit.allowed) {
    return jsonError(
      rateLimit.unavailable ? "Rate limit indisponible." : "Trop de tentatives. Reessayez dans quelques instants.",
      rateLimit.unavailable ? 503 : 429
    );
  }

  try {
    const payload = checkoutSchema.parse(await request.json());
    const stripe = getStripe();
    const stripeCustomerId = await ensureStripeCustomerForUser(user);
    const appUrl = getAppUrl();

    if (payload.licenseId) {
      const license = await prisma.license.findFirst({
        where: { id: payload.licenseId, ownerId: user.id }
      });

      if (!license) {
        return jsonError("Licence introuvable.", 404);
      }

      const metadata = buildCheckoutMetadata({
        checkoutType: "renew",
        userId: user.id,
        licenseId: license.id,
        publicId: license.publicId,
        product: license.product,
        maxActivations: license.deviceLimit,
        seatCount: license.seatCount
      });

      const session = await stripe.checkout.sessions.create({
        mode: "subscription",
        customer: stripeCustomerId,
        line_items: [
          {
            price: getStripePriceIdForProduct(license.product),
            quantity: 1
          }
        ],
        allow_promotion_codes: true,
        client_reference_id: license.id,
        metadata,
        subscription_data: { metadata },
        success_url: `${appUrl}/licenses/${license.id}?checkout=success`,
        cancel_url: `${appUrl}/licenses/${license.id}?checkout=cancelled`
      });

      return NextResponse.json({ url: session.url });
    }

    const product = normalizeProductCode(payload.product);
    const maxActivations = payload.maxActivations ?? (product === "SERVER" ? 1 : 3);
    const seatCount = payload.seatCount ?? maxActivations;
    const metadata = buildCheckoutMetadata({
      checkoutType: "purchase",
      userId: user.id,
      product,
      maxActivations,
      seatCount
    });

    const session = await stripe.checkout.sessions.create({
      mode: "subscription",
      customer: stripeCustomerId,
      line_items: [
        {
          price: getStripePriceIdForProduct(product),
          quantity: 1
        }
      ],
      allow_promotion_codes: true,
      client_reference_id: user.id,
      metadata,
      subscription_data: { metadata },
      success_url: `${appUrl}/licenses?checkout=success`,
      cancel_url: `${appUrl}/licenses?checkout=cancelled`
    });

    return NextResponse.json({ url: session.url });
  } catch (error) {
    return validationError(error);
  }
}
