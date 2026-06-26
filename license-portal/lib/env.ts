export function getEnv(name: string, fallback?: string) {
  const value = process.env[name] ?? fallback;

  if (!value && process.env.NODE_ENV === "production") {
    throw new Error(`Missing required environment variable: ${name}`);
  }

  return value ?? "";
}

export function requireEnv(name: string) {
  const value = process.env[name];

  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }

  return value;
}

export function getAppUrl() {
  return getEnv("APP_URL", "http://localhost:3000").replace(/\/$/, "");
}

export function getAuthSecret() {
  return getEnv("AUTH_SECRET", "dev-only-auth-secret-change-before-production-32");
}

export function getLicenseHashSecret() {
  return getEnv("LICENSE_HASH_SECRET", "dev-only-license-secret-change-before-prod");
}

export function getLicenseKeyEncryptionSecret() {
  const value = process.env.LICENSE_KEY_ENCRYPTION_SECRET;

  if (value) {
    return value;
  }

  if (process.env.NODE_ENV === "production") {
    throw new Error("Missing required environment variable: LICENSE_KEY_ENCRYPTION_SECRET");
  }

  return getLicenseHashSecret();
}
