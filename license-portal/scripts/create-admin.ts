import bcrypt from "bcryptjs";
import { PrismaClient, UserRole } from "@prisma/client";
import { z } from "zod";

const prisma = new PrismaClient();

const adminSchema = z.object({
  email: z.string().email().toLowerCase(),
  name: z.string().min(2).max(120),
  company: z.string().min(2).max(160).optional(),
  password: z
    .string()
    .min(14)
    .refine((value) => /[a-z]/.test(value), "Le mot de passe doit contenir une minuscule.")
    .refine((value) => /[A-Z]/.test(value), "Le mot de passe doit contenir une majuscule.")
    .refine((value) => /\d/.test(value), "Le mot de passe doit contenir un chiffre.")
    .refine((value) => /[^A-Za-z0-9]/.test(value), "Le mot de passe doit contenir un symbole.")
});

function readAdminInput() {
  return adminSchema.parse({
    email: process.env.ADMIN_EMAIL,
    name: process.env.ADMIN_NAME,
    company: process.env.ADMIN_COMPANY || undefined,
    password: process.env.ADMIN_PASSWORD
  });
}

async function main() {
  const input = readAdminInput();
  const existing = await prisma.user.findUnique({
    where: { email: input.email }
  });

  if (existing?.role === UserRole.ADMIN) {
    console.log(`Admin deja existant: ${input.email}`);
    return;
  }

  if (existing) {
    throw new Error(
      `Un utilisateur existe deja avec ${input.email}. Refus de promotion automatique; faites une operation admin explicite.`
    );
  }

  const passwordHash = await bcrypt.hash(input.password, 12);
  const admin = await prisma.$transaction(async (tx) => {
    const user = await tx.user.create({
      data: {
        email: input.email,
        name: input.name,
        company: input.company,
        role: UserRole.ADMIN,
        passwordHash
      }
    });

    await tx.auditLog.create({
      data: {
        actorId: user.id,
        action: "ADMIN_CREATED",
        target: user.id,
        metadata: {
          email: user.email,
          source: "scripts/create-admin.ts"
        }
      }
    });

    return user;
  });

  console.log(`Admin cree: ${admin.email} (${admin.id})`);
}

main()
  .catch((error) => {
    if (error instanceof z.ZodError) {
      console.error("Variables ADMIN_* invalides:");
      console.error(error.flatten().fieldErrors);
    } else {
      console.error(error instanceof Error ? error.message : error);
    }

    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
