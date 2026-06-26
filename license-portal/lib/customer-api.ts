import { PortalDevice, PortalInvoice } from "@/lib/portal-types";

export type CustomerUser = {
  id: string;
  email: string;
  name: string;
  company?: string | null;
  role: string;
};

export type CustomerLicense = {
  id: string;
  publicId: string;
  keyPrefix: string;
  licenseKeyAvailable?: boolean;
  licenseKeyRevealedAt?: string | null;
  product: string;
  status: string;
  expiresAt: string;
  maxActivations: number;
  activeActivations: number;
  remainingActivations: number;
  seats: number;
  subscriptionId?: string | null;
  devices: PortalDevice[];
  invoices: PortalInvoice[];
  createdAt: string;
  updatedAt: string;
};

type ApiErrorPayload = {
  error?: string;
  details?: unknown;
};

export class ApiRequestError extends Error {
  status: number;
  details?: unknown;

  constructor(message: string, status: number, details?: unknown) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.details = details;
  }
}

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: "include",
    ...options,
    headers: {
      ...(options?.body ? { "Content-Type": "application/json" } : {}),
      ...options?.headers
    }
  });

  const data = (await response.json().catch(() => ({}))) as ApiErrorPayload;

  if (!response.ok) {
    throw new ApiRequestError(data.error ?? "Action impossible.", response.status, data.details);
  }

  return data as T;
}

export function normalizeLicenseStatus(status: string) {
  return status.toUpperCase();
}

export function activeDevices(license: CustomerLicense) {
  return license.devices.filter((device) => !device.deactivatedAt);
}

export function allActiveDevices(licenses: CustomerLicense[]) {
  return licenses.flatMap((license) =>
    activeDevices(license).map((device) => ({
      ...device,
      licenseId: license.id,
      licensePublicId: license.publicId,
      product: license.product
    }))
  );
}

export async function getCustomerLicenses() {
  const data = await apiFetch<{ licenses: CustomerLicense[] }>("/api/customer/licenses");
  return data.licenses;
}

export async function getCustomerLicense(id: string) {
  const data = await apiFetch<{ license: CustomerLicense }>(`/api/customer/licenses/${id}`);
  return data.license;
}

export async function getCustomerInvoices() {
  const data = await apiFetch<{ invoices: PortalInvoice[] }>("/api/invoices");
  return data.invoices;
}

export async function getCurrentCustomer() {
  const data = await apiFetch<{ user: CustomerUser }>("/api/auth/me");
  return data.user;
}
