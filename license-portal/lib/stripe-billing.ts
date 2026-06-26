import Stripe from "stripe";
import { Prisma } from "@prisma/client";
import { prisma } from "@/lib/db";
import { getEnv, requireEnv } from "@/lib/env";
import { sendLicenseKeyEmail } from "@/lib/license-email";
import { encryptLicenseKey } from "@/lib/license-key-delivery";
import { buildPublicLicenseId, generateLicenseKey, hashLicenseKey } from "@/lib/license";
import { getStripe } from "@/lib/stripe";

const PRODUCT_CODES = ["ENDPOINT", "SERVER", "MOBILE"] as const;
const CHECKOUT_TYPES = ["purchase", "renew"] as const;

export type StripeProductCode = (typeof PRODUCT_CODES)[number];
export type StripeCheckoutType = (typeof CHECKOUT_TYPES)[number];

type StripeBillingUser = {
  id: string;
  email: string;
  name: string;
  company?: string | null;
  stripeCustomerId?: string | null;
};

type CheckoutMetadataInput = {
  checkoutType: StripeCheckoutType;
  userId: string;
  licenseId?: string;
  publicId?: string;
  product?: StripeProductCode;
  maxActivations?: number;
  seatCount?: number;
};

type CreatedLicenseDelivery = {
  license: Awaited<ReturnType<Prisma.TransactionClient["license"]["create"]>>;
  created: boolean;
};

type InvoiceLike = Stripe.Invoice & {
  amount_due?: number | null;
  amount_paid?: number | null;
  due_date?: number | null;
  hosted_invoice_url?: string | null;
  invoice_pdf?: string | null;
  number?: string | null;
  paid?: boolean | null;
  payment_intent?: string | Stripe.PaymentIntent | null;
  period_end?: number | null;
  subscription?: string | Stripe.Subscription | null;
};

const PRODUCT_DEFAULTS: Record<StripeProductCode, { maxActivations: number; seatCount: number }> = {
  ENDPOINT: { maxActivations: 3, seatCount: 3 },
  SERVER: { maxActivations: 1, seatCount: 1 },
  MOBILE: { maxActivations: 3, seatCount: 3 }
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function metadataValue(value: string | number | undefined | null) {
  return value === undefined || value === null ? undefined : String(value);
}

function compactMetadata(metadata: Record<string, string | undefined>) {
  return Object.fromEntries(
    Object.entries(metadata).filter((entry): entry is [string, string] => Boolean(entry[1]))
  );
}

function clampInt(value: unknown, fallback: number, min = 1, max = 500) {
  const numeric = typeof value === "number" ? value : Number.parseInt(String(value ?? ""), 10);

  if (!Number.isFinite(numeric)) {
    return fallback;
  }

  return Math.min(Math.max(Math.trunc(numeric), min), max);
}

export function normalizeProductCode(value: unknown): StripeProductCode {
  return PRODUCT_CODES.includes(value as StripeProductCode) ? (value as StripeProductCode) : "ENDPOINT";
}

export function buildCheckoutMetadata(input: CheckoutMetadataInput) {
  return compactMetadata({
    checkoutType: input.checkoutType,
    userId: input.userId,
    licenseId: input.licenseId,
    publicId: input.publicId,
    product: input.product,
    maxActivations: metadataValue(input.maxActivations),
    seatCount: metadataValue(input.seatCount)
  });
}

export function normalizePurchaseMetadata(metadata: Stripe.Metadata | null | undefined) {
  const product = normalizeProductCode(metadata?.product);
  const defaults = PRODUCT_DEFAULTS[product];
  const maxActivations = clampInt(metadata?.maxActivations, defaults.maxActivations);
  const seatCount = clampInt(metadata?.seatCount, maxActivations);

  return {
    product,
    maxActivations,
    seatCount
  };
}

export function shouldCreateLicenseAfterPayment(metadata: Stripe.Metadata | null | undefined) {
  return metadata?.checkoutType === "purchase" && Boolean(metadata.userId) && !metadata.licenseId;
}

export function getStripePriceIdForProduct(product: StripeProductCode) {
  const envName =
    product === "SERVER"
      ? "STRIPE_SERVER_PRICE_ID"
      : product === "MOBILE"
        ? "STRIPE_MOBILE_PRICE_ID"
        : "STRIPE_ENDPOINT_PRICE_ID";

  return getEnv(envName) || requireEnv("STRIPE_PRICE_ID");
}

export function mapStripeSubscriptionStatus(status: string) {
  return status === "active" || status === "trialing" ? "ACTIVE" : "SUSPENDED";
}

export function getStripeObjectId(value: unknown) {
  if (typeof value === "string") {
    return value;
  }

  const record = asRecord(value);
  return typeof record.id === "string" ? record.id : undefined;
}

export function getSubscriptionPeriodEnd(subscription: Stripe.Subscription) {
  const record = asRecord(subscription);
  const directPeriodEnd = record.current_period_end;
  const items = asRecord(record.items);
  const data = Array.isArray(items.data) ? items.data : [];
  const firstItemPeriodEnd = asRecord(data[0]).current_period_end;
  const periodEnd = typeof directPeriodEnd === "number" ? directPeriodEnd : firstItemPeriodEnd;

  return typeof periodEnd === "number" ? new Date(periodEnd * 1000) : null;
}

export async function ensureStripeCustomerForUser(user: StripeBillingUser) {
  if (user.stripeCustomerId) {
    return user.stripeCustomerId;
  }

  const stripe = getStripe();
  const customer = await stripe.customers.create({
    email: user.email,
    name: user.name,
    metadata: { userId: user.id }
  });

  await prisma.user.update({
    where: { id: user.id },
    data: { stripeCustomerId: customer.id }
  });

  return customer.id;
}

export async function handleStripeWebhookEvent(event: Stripe.Event) {
  switch (event.type) {
    case "checkout.session.completed":
      await handleCheckoutSessionCompleted(event.data.object as Stripe.Checkout.Session);
      break;
    case "invoice.paid":
    case "invoice.payment_succeeded":
      await handleInvoicePaymentSucceeded(event.data.object as InvoiceLike);
      break;
    case "payment_intent.succeeded":
      await handlePaymentIntentSucceeded(event.data.object as Stripe.PaymentIntent);
      break;
    case "customer.subscription.created":
    case "customer.subscription.updated":
      await handleSubscriptionSynced(event.data.object as Stripe.Subscription);
      break;
    case "customer.subscription.deleted":
      await handleSubscriptionCancelled(event.data.object as Stripe.Subscription);
      break;
    default:
      break;
  }
}

export async function handleCheckoutSessionCompleted(session: Stripe.Checkout.Session) {
  const metadata = session.metadata ?? {};
  const userId = metadata.userId;
  const subscriptionId = getStripeObjectId(session.subscription);
  const customerId = getStripeObjectId(session.customer);
  const user = await resolveWebhookUser({ userId, customerId });

  if (user && customerId) {
    await linkStripeCustomer(user.id, customerId);
  }

  if (metadata.licenseId && user) {
    await prisma.license.updateMany({
      where: { id: metadata.licenseId, ownerId: user.id },
      data: {
        subscriptionId,
        ...(session.payment_status === "paid" ? { status: "ACTIVE" } : {})
      }
    });
  }

  if (user) {
    await upsertPaymentFromCheckoutSession(session, user.id, subscriptionId);
  }
}

export async function handleInvoicePaymentSucceeded(invoice: InvoiceLike) {
  if (!invoice.id || !isPaidInvoice(invoice)) {
    return;
  }

  const subscriptionId = getInvoiceSubscriptionId(invoice);
  const subscription = subscriptionId ? await retrieveSubscription(subscriptionId) : null;
  const metadata = mergeMetadata(invoice.metadata, subscription?.metadata);
  const customerId = getStripeObjectId(invoice.customer) ?? getStripeObjectId(subscription?.customer);
  const user = await resolveWebhookUser({ userId: metadata.userId, customerId });

  if (!user) {
    return;
  }

  if (customerId) {
    await linkStripeCustomer(user.id, customerId);
  }

  const license = await resolvePaidInvoiceLicense({ user, invoice, subscription, metadata });

  await upsertInvoiceFromStripe(invoice, user.id, license?.id);
  await upsertPaymentFromInvoice(invoice, user.id, subscriptionId);

  if (subscription) {
    await syncSubscriptionToLicense(subscription, license?.id);
  }
}

export async function handlePaymentIntentSucceeded(paymentIntent: Stripe.PaymentIntent) {
  if (!paymentIntent.id) {
    return;
  }

  const customerId = getStripeObjectId(paymentIntent.customer);
  const user = await resolveWebhookUser({ userId: paymentIntent.metadata?.userId, customerId });

  await upsertPaymentFromPaymentIntent(paymentIntent, user?.id);
}

export async function handleSubscriptionSynced(subscription: Stripe.Subscription) {
  await syncSubscriptionToLicense(subscription);
}

export async function handleSubscriptionCancelled(subscription: Stripe.Subscription) {
  const license = await findLicenseForSubscription(subscription);

  if (!license) {
    return;
  }

  const expiresAt = getSubscriptionPeriodEnd(subscription) ?? new Date();

  await prisma.$transaction([
    prisma.license.update({
      where: { id: license.id },
      data: {
        status: "SUSPENDED",
        subscriptionId: subscription.id,
        expiresAt
      }
    }),
    prisma.auditLog.create({
      data: {
        actorId: license.ownerId,
        action: "STRIPE_SUBSCRIPTION_CANCELLED",
        target: license.publicId,
        metadata: { subscriptionId: subscription.id }
      }
    })
  ]);
}

async function syncSubscriptionToLicense(subscription: Stripe.Subscription, knownLicenseId?: string) {
  const license =
    knownLicenseId
      ? await prisma.license.findUnique({ where: { id: knownLicenseId } })
      : await findLicenseForSubscription(subscription);

  if (!license) {
    return null;
  }

  const expiresAt = getSubscriptionPeriodEnd(subscription);
  const latestInvoiceId = getStripeObjectId(subscription.latest_invoice);

  await prisma.license.update({
    where: { id: license.id },
    data: {
      status: mapStripeSubscriptionStatus(subscription.status),
      subscriptionId: subscription.id,
      latestInvoiceId,
      ...(expiresAt ? { expiresAt } : {})
    }
  });

  return license;
}

async function resolvePaidInvoiceLicense({
  user,
  invoice,
  subscription,
  metadata
}: {
  user: StripeBillingUser;
  invoice: InvoiceLike;
  subscription: Stripe.Subscription | null;
  metadata: Stripe.Metadata;
}) {
  const subscriptionId = subscription?.id ?? getInvoiceSubscriptionId(invoice);

  if (metadata.licenseId) {
    const license = await prisma.license.findFirst({
      where: { id: metadata.licenseId, ownerId: user.id }
    });

    if (license && subscription) {
      await syncSubscriptionToLicense(subscription, license.id);
    }

    return license;
  }

  if (subscriptionId) {
    const existing = await prisma.license.findUnique({
      where: { subscriptionId }
    });

    if (existing) {
      return existing;
    }
  }

  if (!subscription || !subscriptionId || !shouldCreateLicenseAfterPayment(metadata)) {
    return null;
  }

  return createLicenseFromPaidSubscription({ user, invoice, subscription, metadata });
}

async function createLicenseFromPaidSubscription({
  user,
  invoice,
  subscription,
  metadata
}: {
  user: StripeBillingUser;
  invoice: InvoiceLike;
  subscription: Stripe.Subscription;
  metadata: Stripe.Metadata;
}) {
  const purchase = normalizePurchaseMetadata(metadata);
  const expiresAt = getSubscriptionPeriodEnd(subscription) ?? getInvoicePeriodEnd(invoice) ?? addOneYear(new Date());
  const rawLicenseKey = generateLicenseKey();
  const keyHash = hashLicenseKey(rawLicenseKey);
  const keyPrefix = rawLicenseKey.split("-")[0] ?? "XXXX";

  const result = await prisma.$transaction(async (tx): Promise<CreatedLicenseDelivery> => {
    const existing = await tx.license.findUnique({
      where: { subscriptionId: subscription.id }
    });

    if (existing) {
      return { license: existing, created: false };
    }

    const keyCollision = await tx.license.findUnique({
      where: { keyHash }
    });

    if (keyCollision) {
      throw new Error("Stripe license key collision. Retry webhook delivery.");
    }

    const publicId = await buildUniquePublicLicenseId(tx, user);
    const license = await tx.license.create({
      data: {
        publicId,
        keyHash,
        keyPrefix,
        encryptedLicenseKey: encryptLicenseKey(rawLicenseKey),
        licenseKeyRevealedAt: null,
        product: purchase.product,
        status: mapStripeSubscriptionStatus(subscription.status),
        expiresAt,
        deviceLimit: purchase.maxActivations,
        seatCount: purchase.seatCount,
        subscriptionId: subscription.id,
        latestInvoiceId: invoice.id,
        ownerId: user.id
      }
    });

    await tx.licenseValidation.create({
      data: {
        licenseId: license.id,
        action: "CREATED",
        result: "ALLOWED",
        reason: "Licence creee automatiquement apres paiement Stripe"
      }
    });

    await tx.auditLog.create({
      data: {
        actorId: user.id,
        action: "LICENSE_CREATED_FROM_STRIPE",
        target: license.publicId,
        metadata: {
          subscriptionId: subscription.id,
          invoiceId: invoice.id,
          product: purchase.product,
          keyPrefix,
          rawKeyDelivery: "encrypted_one_time"
        }
      }
    });

    await tx.auditLog.create({
      data: {
        actorId: user.id,
        action: "LICENSE_KEY_STAGED_FOR_REVEAL",
        target: license.publicId,
        metadata: {
          subscriptionId: subscription.id,
          invoiceId: invoice.id,
          keyPrefix,
          delivery: "encrypted_one_time"
        }
      }
    });

    return { license, created: true };
  });

  if (result.created) {
    await deliverLicenseKeyEmail({
      user,
      license: result.license,
      rawLicenseKey,
      product: purchase.product,
      expiresAt,
      maxActivations: purchase.maxActivations,
      seatCount: purchase.seatCount,
      invoiceId: invoice.id,
      subscriptionId: subscription.id
    });
  }

  return result.license;
}

async function deliverLicenseKeyEmail({
  user,
  license,
  rawLicenseKey,
  product,
  expiresAt,
  maxActivations,
  seatCount,
  invoiceId,
  subscriptionId
}: {
  user: StripeBillingUser;
  license: { publicId: string };
  rawLicenseKey: string;
  product: StripeProductCode;
  expiresAt: Date;
  maxActivations: number;
  seatCount: number;
  invoiceId?: string;
  subscriptionId: string;
}) {
  try {
    const result = await sendLicenseKeyEmail({
      to: user.email,
      customerName: user.name,
      publicId: license.publicId,
      product,
      expiresAt,
      maxActivations,
      seatCount,
      licenseKey: rawLicenseKey
    });

    await auditLicenseEmailDelivery("LICENSE_KEY_EMAIL_SENT", user.id, license.publicId, {
      provider: result.provider,
      messageId: result.messageId,
      invoiceId,
      subscriptionId,
      product,
      keyPrefix: rawLicenseKey.split("-")[0] ?? "XXXX"
    });
  } catch (error) {
    await auditLicenseEmailDelivery("LICENSE_KEY_EMAIL_FAILED", user.id, license.publicId, {
      invoiceId,
      subscriptionId,
      product,
      keyPrefix: rawLicenseKey.split("-")[0] ?? "XXXX",
      error: error instanceof Error ? error.message : "Unknown email delivery error"
    });
  }
}

async function auditLicenseEmailDelivery(
  action: "LICENSE_KEY_EMAIL_SENT" | "LICENSE_KEY_EMAIL_FAILED",
  actorId: string,
  target: string,
  metadata: Record<string, unknown>
) {
  try {
    await prisma.auditLog.create({
      data: {
        actorId,
        action,
        target,
        metadata: compactAuditMetadata(metadata)
      }
    });
  } catch (error) {
    console.error("Unable to write license email audit log.", error);
  }
}

function compactAuditMetadata(metadata: Record<string, unknown>): Prisma.InputJsonObject {
  return Object.fromEntries(Object.entries(metadata).filter(([, value]) => value !== undefined)) as Prisma.InputJsonObject;
}

async function buildUniquePublicLicenseId(
  tx: Prisma.TransactionClient,
  user: StripeBillingUser
) {
  const count = await tx.license.count({ where: { ownerId: user.id } });

  for (let offset = 1; offset <= 25; offset += 1) {
    const publicId = buildPublicLicenseId(user.company ?? user.name, count + offset);
    const existing = await tx.license.findUnique({ where: { publicId } });

    if (!existing) {
      return publicId;
    }
  }

  throw new Error("Unable to generate a unique public license id.");
}

async function findLicenseForSubscription(subscription: Stripe.Subscription) {
  const licenseId = subscription.metadata?.licenseId;

  if (licenseId) {
    const license = await prisma.license.findUnique({ where: { id: licenseId } });

    if (license) {
      return license;
    }
  }

  return prisma.license.findUnique({
    where: { subscriptionId: subscription.id }
  });
}

async function retrieveSubscription(subscriptionId: string) {
  try {
    return await getStripe().subscriptions.retrieve(subscriptionId);
  } catch {
    return null;
  }
}

async function resolveWebhookUser({
  userId,
  customerId
}: {
  userId?: string;
  customerId?: string;
}) {
  if (customerId) {
    const byCustomer = await prisma.user.findUnique({
      where: { stripeCustomerId: customerId }
    });

    if (byCustomer) {
      return byCustomer;
    }
  }

  if (!userId) {
    return null;
  }

  return prisma.user.findUnique({
    where: { id: userId }
  });
}

async function linkStripeCustomer(userId: string, customerId: string) {
  const user = await prisma.user.findUnique({ where: { id: userId } });

  if (!user || user.stripeCustomerId === customerId) {
    return;
  }

  if (!user.stripeCustomerId) {
    await prisma.user.update({
      where: { id: userId },
      data: { stripeCustomerId: customerId }
    });
  }
}

async function upsertInvoiceFromStripe(invoice: InvoiceLike, userId: string, licenseId?: string) {
  if (!invoice.id) {
    return;
  }

  const paidAt = getInvoicePaidAt(invoice);

  await prisma.invoice.upsert({
    where: { stripeInvoiceId: invoice.id },
    update: {
      userId,
      licenseId,
      number: invoice.number ?? invoice.id,
      amountCents: invoice.amount_paid ?? invoice.amount_due ?? 0,
      currency: invoice.currency ?? "eur",
      status: invoice.status ?? "paid",
      hostedInvoiceUrl: invoice.hosted_invoice_url ?? undefined,
      invoicePdfUrl: invoice.invoice_pdf ?? undefined,
      paidAt,
      dueAt: getInvoiceDueAt(invoice)
    },
    create: {
      userId,
      licenseId,
      stripeInvoiceId: invoice.id,
      number: invoice.number ?? invoice.id,
      amountCents: invoice.amount_paid ?? invoice.amount_due ?? 0,
      currency: invoice.currency ?? "eur",
      status: invoice.status ?? "paid",
      hostedInvoiceUrl: invoice.hosted_invoice_url ?? undefined,
      invoicePdfUrl: invoice.invoice_pdf ?? undefined,
      paidAt,
      dueAt: getInvoiceDueAt(invoice)
    }
  });
}

async function upsertPaymentFromCheckoutSession(
  session: Stripe.Checkout.Session,
  userId: string,
  subscriptionId?: string
) {
  await prisma.payment.upsert({
    where: { stripeCheckoutSessionId: session.id },
    update: {
      userId,
      stripeSubscriptionId: subscriptionId,
      amountCents: session.amount_total ?? 0,
      currency: session.currency ?? "eur",
      status: session.payment_status ?? "paid",
      method: "checkout"
    },
    create: {
      userId,
      stripeCheckoutSessionId: session.id,
      stripeSubscriptionId: subscriptionId,
      amountCents: session.amount_total ?? 0,
      currency: session.currency ?? "eur",
      status: session.payment_status ?? "paid",
      method: "checkout"
    }
  });
}

async function upsertPaymentFromInvoice(invoice: InvoiceLike, userId: string, subscriptionId?: string) {
  if (!invoice.id) {
    return;
  }

  const paymentIntentId = getStripeObjectId(invoice.payment_intent);
  const existingByPaymentIntent = paymentIntentId
    ? await prisma.payment.findUnique({ where: { stripePaymentIntentId: paymentIntentId } })
    : null;

  const data = {
    userId,
    stripeInvoiceId: invoice.id,
    stripePaymentIntentId: paymentIntentId,
    stripeSubscriptionId: subscriptionId,
    amountCents: invoice.amount_paid ?? invoice.amount_due ?? 0,
    currency: invoice.currency ?? "eur",
    status: invoice.status ?? "paid",
    method: "stripe_invoice"
  };

  if (existingByPaymentIntent) {
    await prisma.payment.update({
      where: { id: existingByPaymentIntent.id },
      data
    });
    return;
  }

  await prisma.payment.upsert({
    where: { stripeInvoiceId: invoice.id },
    update: data,
    create: data
  });
}

async function upsertPaymentFromPaymentIntent(paymentIntent: Stripe.PaymentIntent, userId?: string) {
  const invoiceId = getStripeObjectId(asRecord(paymentIntent).invoice);

  await prisma.payment.upsert({
    where: { stripePaymentIntentId: paymentIntent.id },
    update: {
      userId,
      stripeInvoiceId: invoiceId,
      amountCents: paymentIntent.amount_received || paymentIntent.amount,
      currency: paymentIntent.currency ?? "eur",
      status: paymentIntent.status,
      method: paymentIntent.payment_method_types?.[0] ?? "stripe"
    },
    create: {
      userId,
      stripePaymentIntentId: paymentIntent.id,
      stripeInvoiceId: invoiceId,
      amountCents: paymentIntent.amount_received || paymentIntent.amount,
      currency: paymentIntent.currency ?? "eur",
      status: paymentIntent.status,
      method: paymentIntent.payment_method_types?.[0] ?? "stripe"
    }
  });
}

function getInvoiceSubscriptionId(invoice: InvoiceLike) {
  const direct = getStripeObjectId(invoice.subscription);

  if (direct) {
    return direct;
  }

  const parent = asRecord(asRecord(invoice).parent);
  const subscriptionDetails = asRecord(parent.subscription_details);

  return getStripeObjectId(subscriptionDetails.subscription);
}

function mergeMetadata(...items: Array<Stripe.Metadata | null | undefined>) {
  return Object.assign({}, ...items.filter(Boolean)) as Stripe.Metadata;
}

function isPaidInvoice(invoice: InvoiceLike) {
  return invoice.status === "paid" || invoice.paid === true;
}

function getInvoicePaidAt(invoice: InvoiceLike) {
  const paidAt = asRecord(invoice.status_transitions).paid_at;
  return typeof paidAt === "number" ? new Date(paidAt * 1000) : undefined;
}

function getInvoiceDueAt(invoice: InvoiceLike) {
  return typeof invoice.due_date === "number" ? new Date(invoice.due_date * 1000) : undefined;
}

function getInvoicePeriodEnd(invoice: InvoiceLike) {
  return typeof invoice.period_end === "number" ? new Date(invoice.period_end * 1000) : null;
}

function addOneYear(date: Date) {
  const next = new Date(date);
  next.setFullYear(next.getFullYear() + 1);
  return next;
}
