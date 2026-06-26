CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TYPE "UserRole" AS ENUM ('CUSTOMER', 'ADMIN');
CREATE TYPE "LicenseStatus" AS ENUM ('ACTIVE', 'EXPIRED', 'SUSPENDED', 'REVOKED');
CREATE TYPE "ProductCode" AS ENUM ('ENDPOINT', 'SERVER', 'MOBILE');
CREATE TYPE "ValidationResult" AS ENUM ('ALLOWED', 'DENIED');
CREATE TYPE "ValidationAction" AS ENUM (
  'CREATED',
  'VALIDATED',
  'DEVICE_ACTIVATED',
  'DEVICE_REACTIVATED',
  'DEVICE_LIMIT_REACHED',
  'EXPIRED_DENIED',
  'SUSPENDED_DENIED',
  'REVOKED_DENIED',
  'NOT_FOUND'
);

CREATE TABLE "User" (
  "id" UUID NOT NULL DEFAULT gen_random_uuid(),
  "email" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "company" TEXT,
  "passwordHash" TEXT NOT NULL,
  "role" "UserRole" NOT NULL DEFAULT 'CUSTOMER',
  "stripeCustomerId" TEXT,
  "passwordResetTokenHash" TEXT,
  "passwordResetTokenExpiry" TIMESTAMP(3),
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,

  CONSTRAINT "User_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "License" (
  "id" UUID NOT NULL DEFAULT gen_random_uuid(),
  "publicId" TEXT NOT NULL,
  "keyHash" TEXT NOT NULL,
  "keyPrefix" TEXT NOT NULL,
  "encryptedLicenseKey" TEXT,
  "licenseKeyRevealedAt" TIMESTAMP(3),
  "product" "ProductCode" NOT NULL,
  "status" "LicenseStatus" NOT NULL DEFAULT 'ACTIVE',
  "expiresAt" TIMESTAMP(3) NOT NULL,
  "deviceLimit" INTEGER NOT NULL,
  "seatCount" INTEGER NOT NULL,
  "subscriptionId" TEXT,
  "latestInvoiceId" TEXT,
  "ownerId" UUID NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,

  CONSTRAINT "License_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "Device" (
  "id" UUID NOT NULL DEFAULT gen_random_uuid(),
  "licenseId" UUID NOT NULL,
  "fingerprintHash" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "platform" TEXT,
  "activatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "deactivatedAt" TIMESTAMP(3),
  "lastSeenAt" TIMESTAMP(3),

  CONSTRAINT "Device_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "LicenseValidation" (
  "id" UUID NOT NULL DEFAULT gen_random_uuid(),
  "licenseId" UUID,
  "deviceId" UUID,
  "fingerprintHash" TEXT,
  "action" "ValidationAction" NOT NULL,
  "result" "ValidationResult" NOT NULL,
  "reason" TEXT,
  "ipHash" TEXT,
  "userAgent" TEXT,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT "LicenseValidation_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "Invoice" (
  "id" UUID NOT NULL DEFAULT gen_random_uuid(),
  "userId" UUID NOT NULL,
  "licenseId" UUID,
  "stripeInvoiceId" TEXT,
  "number" TEXT NOT NULL,
  "amountCents" INTEGER NOT NULL,
  "currency" TEXT NOT NULL DEFAULT 'eur',
  "status" TEXT NOT NULL,
  "hostedInvoiceUrl" TEXT,
  "invoicePdfUrl" TEXT,
  "paidAt" TIMESTAMP(3),
  "dueAt" TIMESTAMP(3),
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT "Invoice_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "Payment" (
  "id" UUID NOT NULL DEFAULT gen_random_uuid(),
  "userId" UUID,
  "stripePaymentIntentId" TEXT,
  "stripeInvoiceId" TEXT,
  "stripeSubscriptionId" TEXT,
  "stripeCheckoutSessionId" TEXT,
  "amountCents" INTEGER NOT NULL,
  "currency" TEXT NOT NULL DEFAULT 'eur',
  "status" TEXT NOT NULL,
  "method" TEXT,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT "Payment_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "AuditLog" (
  "id" UUID NOT NULL DEFAULT gen_random_uuid(),
  "actorId" UUID,
  "action" TEXT NOT NULL,
  "target" TEXT NOT NULL,
  "metadata" JSONB,
  "ipHash" TEXT,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT "AuditLog_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "User_email_key" ON "User"("email");
CREATE UNIQUE INDEX "User_stripeCustomerId_key" ON "User"("stripeCustomerId");

CREATE UNIQUE INDEX "License_publicId_key" ON "License"("publicId");
CREATE UNIQUE INDEX "License_keyHash_key" ON "License"("keyHash");
CREATE UNIQUE INDEX "License_subscriptionId_key" ON "License"("subscriptionId");
CREATE INDEX "License_ownerId_idx" ON "License"("ownerId");
CREATE INDEX "License_status_idx" ON "License"("status");
CREATE INDEX "License_expiresAt_idx" ON "License"("expiresAt");

CREATE UNIQUE INDEX "Device_licenseId_fingerprintHash_key" ON "Device"("licenseId", "fingerprintHash");
CREATE INDEX "Device_licenseId_deactivatedAt_idx" ON "Device"("licenseId", "deactivatedAt");

CREATE INDEX "LicenseValidation_licenseId_createdAt_idx" ON "LicenseValidation"("licenseId", "createdAt");
CREATE INDEX "LicenseValidation_fingerprintHash_createdAt_idx" ON "LicenseValidation"("fingerprintHash", "createdAt");

CREATE UNIQUE INDEX "Invoice_stripeInvoiceId_key" ON "Invoice"("stripeInvoiceId");
CREATE INDEX "Invoice_userId_createdAt_idx" ON "Invoice"("userId", "createdAt");
CREATE INDEX "Invoice_licenseId_idx" ON "Invoice"("licenseId");

CREATE UNIQUE INDEX "Payment_stripePaymentIntentId_key" ON "Payment"("stripePaymentIntentId");
CREATE UNIQUE INDEX "Payment_stripeInvoiceId_key" ON "Payment"("stripeInvoiceId");
CREATE UNIQUE INDEX "Payment_stripeCheckoutSessionId_key" ON "Payment"("stripeCheckoutSessionId");
CREATE INDEX "Payment_userId_createdAt_idx" ON "Payment"("userId", "createdAt");
CREATE INDEX "Payment_stripeSubscriptionId_idx" ON "Payment"("stripeSubscriptionId");

CREATE INDEX "AuditLog_actorId_createdAt_idx" ON "AuditLog"("actorId", "createdAt");
CREATE INDEX "AuditLog_target_idx" ON "AuditLog"("target");

ALTER TABLE "License" ADD CONSTRAINT "License_ownerId_fkey" FOREIGN KEY ("ownerId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "Device" ADD CONSTRAINT "Device_licenseId_fkey" FOREIGN KEY ("licenseId") REFERENCES "License"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "LicenseValidation" ADD CONSTRAINT "LicenseValidation_licenseId_fkey" FOREIGN KEY ("licenseId") REFERENCES "License"("id") ON DELETE SET NULL ON UPDATE CASCADE;
ALTER TABLE "LicenseValidation" ADD CONSTRAINT "LicenseValidation_deviceId_fkey" FOREIGN KEY ("deviceId") REFERENCES "Device"("id") ON DELETE SET NULL ON UPDATE CASCADE;
ALTER TABLE "Invoice" ADD CONSTRAINT "Invoice_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "Invoice" ADD CONSTRAINT "Invoice_licenseId_fkey" FOREIGN KEY ("licenseId") REFERENCES "License"("id") ON DELETE SET NULL ON UPDATE CASCADE;
ALTER TABLE "Payment" ADD CONSTRAINT "Payment_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE SET NULL ON UPDATE CASCADE;
ALTER TABLE "AuditLog" ADD CONSTRAINT "AuditLog_actorId_fkey" FOREIGN KEY ("actorId") REFERENCES "User"("id") ON DELETE SET NULL ON UPDATE CASCADE;
