import { PrismaClient, ProductCode, UserRole } from "@prisma/client";
import { hashPassword } from "../lib/auth";
import { hashFingerprint, hashLicenseKey } from "../lib/license";

const prisma = new PrismaClient();

const rawKeys = {
  endpoint: "ACME-25P7-Q9RK-LM2T",
  server: "ACME-SRV2-7KLM-PQ9R",
  expired: "ACME-EXA2-PQSR-KLRT",
  suspended: "ACME-SUS9-2KLM-8PQR",
  revoked: "ACME-REV4-9KLP-2QRS"
};

async function main() {
  await prisma.auditLog.deleteMany();
  await prisma.payment.deleteMany();
  await prisma.invoice.deleteMany();
  await prisma.licenseValidation.deleteMany();
  await prisma.device.deleteMany();
  await prisma.license.deleteMany();
  await prisma.user.deleteMany();

  const [client, admin] = await Promise.all([
    prisma.user.create({
      data: {
        email: "client@safesweep.test",
        name: "Camille Martin",
        company: "Acme Industries",
        role: UserRole.CUSTOMER,
        passwordHash: await hashPassword("Password123!")
      }
    }),
    prisma.user.create({
      data: {
        email: "admin@safesweep.test",
        name: "Admin SafeSweep",
        company: "SafeSweep",
        role: UserRole.ADMIN,
        passwordHash: await hashPassword("Password123!")
      }
    })
  ]);

  const endpoint = await prisma.license.create({
    data: {
      publicId: "SWP-ACME-0012",
      keyHash: hashLicenseKey(rawKeys.endpoint),
      keyPrefix: rawKeys.endpoint.split("-")[0],
      product: ProductCode.ENDPOINT,
      status: "ACTIVE",
      expiresAt: new Date("2026-08-15T00:00:00.000Z"),
      deviceLimit: 10,
      seatCount: 10,
      ownerId: client.id
    }
  });

  const server = await prisma.license.create({
    data: {
      publicId: "SWP-ACME-0011",
      keyHash: hashLicenseKey(rawKeys.server),
      keyPrefix: rawKeys.server.split("-")[0],
      product: ProductCode.SERVER,
      status: "ACTIVE",
      expiresAt: new Date("2026-11-30T00:00:00.000Z"),
      deviceLimit: 5,
      seatCount: 5,
      ownerId: client.id
    }
  });

  await prisma.license.createMany({
    data: [
      {
        publicId: "SWP-ACME-0010",
        keyHash: hashLicenseKey(rawKeys.expired),
        keyPrefix: rawKeys.expired.split("-")[0],
        product: ProductCode.MOBILE,
        status: "EXPIRED",
        expiresAt: new Date("2025-05-10T00:00:00.000Z"),
        deviceLimit: 3,
        seatCount: 3,
        ownerId: client.id
      },
      {
        publicId: "SWP-ACME-0009",
        keyHash: hashLicenseKey(rawKeys.suspended),
        keyPrefix: rawKeys.suspended.split("-")[0],
        product: ProductCode.ENDPOINT,
        status: "SUSPENDED",
        expiresAt: new Date("2026-09-20T00:00:00.000Z"),
        deviceLimit: 5,
        seatCount: 5,
        ownerId: client.id
      },
      {
        publicId: "SWP-ACME-0008",
        keyHash: hashLicenseKey(rawKeys.revoked),
        keyPrefix: rawKeys.revoked.split("-")[0],
        product: ProductCode.SERVER,
        status: "REVOKED",
        expiresAt: new Date("2025-03-12T00:00:00.000Z"),
        deviceLimit: 2,
        seatCount: 2,
        ownerId: client.id
      }
    ]
  });

  const devices = await prisma.device.createManyAndReturn({
    data: [
      {
        licenseId: endpoint.id,
        fingerprintHash: hashFingerprint("ACME-WS-01"),
        name: "ACME-WS-01",
        platform: "Windows 11",
        lastSeenAt: new Date("2026-06-20T10:00:00.000Z")
      },
      {
        licenseId: endpoint.id,
        fingerprintHash: hashFingerprint("ACME-WS-02"),
        name: "ACME-WS-02",
        platform: "Windows 11",
        lastSeenAt: new Date("2026-06-21T08:25:00.000Z")
      },
      {
        licenseId: endpoint.id,
        fingerprintHash: hashFingerprint("ACME-LAP-07"),
        name: "ACME-LAP-07",
        platform: "Windows 10",
        lastSeenAt: new Date("2026-06-18T12:40:00.000Z")
      },
      {
        licenseId: server.id,
        fingerprintHash: hashFingerprint("ACME-SRV-01"),
        name: "ACME-SRV-01",
        platform: "Windows Server 2022",
        lastSeenAt: new Date("2026-06-22T05:12:00.000Z")
      }
    ]
  });

  await prisma.licenseValidation.createMany({
    data: [
      {
        licenseId: endpoint.id,
        deviceId: devices[0]?.id,
        fingerprintHash: hashFingerprint("ACME-WS-01"),
        action: "CREATED",
        result: "ALLOWED",
        reason: "Licence creee manuellement par l'admin"
      },
      {
        licenseId: endpoint.id,
        deviceId: devices[0]?.id,
        fingerprintHash: hashFingerprint("ACME-WS-01"),
        action: "DEVICE_ACTIVATED",
        result: "ALLOWED",
        reason: "Premiere activation"
      },
      {
        licenseId: endpoint.id,
        deviceId: devices[1]?.id,
        fingerprintHash: hashFingerprint("ACME-WS-02"),
        action: "VALIDATED",
        result: "ALLOWED",
        reason: "Validation reussie"
      },
      {
        licenseId: endpoint.id,
        fingerprintHash: hashFingerprint("UNKNOWN"),
        action: "DEVICE_LIMIT_REACHED",
        result: "DENIED",
        reason: "Limite d'appareils atteinte"
      }
    ]
  });

  await prisma.invoice.createMany({
    data: [
      {
        userId: client.id,
        licenseId: endpoint.id,
        number: "INV-2026-0417",
        amountCents: 125000,
        currency: "eur",
        status: "paid",
        paidAt: new Date("2026-05-15T00:00:00.000Z")
      },
      {
        userId: client.id,
        licenseId: endpoint.id,
        number: "INV-2025-0412",
        amountCents: 115000,
        currency: "eur",
        status: "paid",
        paidAt: new Date("2025-05-15T00:00:00.000Z")
      },
      {
        userId: client.id,
        licenseId: server.id,
        number: "INV-2024-0407",
        amountCents: 105000,
        currency: "eur",
        status: "paid",
        paidAt: new Date("2024-05-15T00:00:00.000Z")
      }
    ]
  });

  await prisma.payment.createMany({
    data: [
      {
        userId: client.id,
        amountCents: 125000,
        currency: "eur",
        status: "paid",
        method: "card"
      },
      {
        userId: client.id,
        amountCents: 95000,
        currency: "eur",
        status: "pending",
        method: "bank_transfer"
      }
    ]
  });

  await prisma.auditLog.create({
    data: {
      actorId: admin.id,
      action: "LICENSE_CREATED",
      target: endpoint.publicId,
      metadata: { userId: client.id }
    }
  });

  console.log("Seed complete.");
  console.log("Client: client@safesweep.test / Password123!");
  console.log("Admin:  admin@safesweep.test / Password123!");
  console.log("Example license key:", rawKeys.endpoint);
}

main()
  .catch((error) => {
    console.error(error);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
