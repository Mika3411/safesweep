import { getEnv } from "@/lib/env";

export type LicenseKeyEmailInput = {
  to: string;
  customerName: string;
  publicId: string;
  product: string;
  expiresAt: Date;
  maxActivations: number;
  seatCount: number;
  licenseKey: string;
};

export type LicenseKeyEmailResult = {
  provider: "resend";
  messageId?: string;
};

function requireEmailEnv(name: string) {
  const value = process.env[name]?.trim();

  if (!value) {
    throw new Error(`Missing required email environment variable: ${name}`);
  }

  return value;
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatDate(value: Date) {
  return new Intl.DateTimeFormat("fr-FR", {
    dateStyle: "long",
    timeZone: "UTC"
  }).format(value);
}

function productLabel(product: string) {
  const labels: Record<string, string> = {
    ENDPOINT: "SafeSweep Endpoint",
    SERVER: "SafeSweep Server",
    MOBILE: "SafeSweep Mobile"
  };

  return labels[product] ?? product;
}

export function buildLicenseKeyEmail(input: LicenseKeyEmailInput) {
  const product = productLabel(input.product);
  const expiresAt = formatDate(input.expiresAt);
  const appUrl = getEnv("APP_URL", "http://localhost:3000");
  const subject = `Votre cle de licence ${product}`;
  const text = [
    `Bonjour ${input.customerName},`,
    "",
    "Votre paiement a bien ete confirme. Voici votre cle de licence :",
    "",
    `Cle : ${input.licenseKey}`,
    `Licence : ${input.publicId}`,
    `Produit : ${product}`,
    `Expiration : ${expiresAt}`,
    `Activations : ${input.maxActivations}`,
    `Sieges : ${input.seatCount}`,
    "",
    `Vous pouvez aussi retrouver votre licence dans votre espace client : ${appUrl}/licenses/${input.publicId}`,
    "",
    "Conservez cette cle dans un endroit sur."
  ].join("\n");
  const html = `
    <div style="font-family: Arial, sans-serif; color: #10212f; line-height: 1.5;">
      <p>Bonjour ${escapeHtml(input.customerName)},</p>
      <p>Votre paiement a bien ete confirme. Voici votre cle de licence :</p>
      <p style="font-size: 20px; font-weight: 700; letter-spacing: 1px; padding: 12px; background: #f4f8fa; border: 1px solid #d7e2e8; border-radius: 6px;">
        ${escapeHtml(input.licenseKey)}
      </p>
      <ul>
        <li><strong>Licence :</strong> ${escapeHtml(input.publicId)}</li>
        <li><strong>Produit :</strong> ${escapeHtml(product)}</li>
        <li><strong>Expiration :</strong> ${escapeHtml(expiresAt)}</li>
        <li><strong>Activations :</strong> ${input.maxActivations}</li>
        <li><strong>Sieges :</strong> ${input.seatCount}</li>
      </ul>
      <p><a href="${escapeHtml(`${appUrl}/licenses/${input.publicId}`)}">Ouvrir mon espace client</a></p>
      <p>Conservez cette cle dans un endroit sur.</p>
    </div>
  `;

  return { subject, text, html };
}

export async function sendLicenseKeyEmail(input: LicenseKeyEmailInput): Promise<LicenseKeyEmailResult> {
  const apiKey = requireEmailEnv("RESEND_API_KEY");
  const from = requireEmailEnv("EMAIL_FROM");
  const replyTo = process.env.EMAIL_REPLY_TO?.trim();
  const endpoint = process.env.RESEND_API_URL?.trim() || "https://api.resend.com/emails";
  const email = buildLicenseKeyEmail(input);
  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      from,
      to: [input.to],
      subject: email.subject,
      text: email.text,
      html: email.html,
      ...(replyTo ? { reply_to: replyTo } : {})
    })
  });
  const payload = (await response.json().catch(() => ({}))) as { id?: string; message?: string; error?: string };

  if (!response.ok) {
    throw new Error(payload.message ?? payload.error ?? `Resend email failed with status ${response.status}`);
  }

  return {
    provider: "resend",
    messageId: payload.id
  };
}
