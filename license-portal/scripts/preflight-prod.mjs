#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REQUIRED_ENV = [
  "DATABASE_URL",
  "AUTH_SECRET",
  "LICENSE_HASH_SECRET",
  "LICENSE_KEY_ENCRYPTION_SECRET",
  "STRIPE_SECRET_KEY",
  "STRIPE_WEBHOOK_SECRET",
  "APP_URL"
];

const OPTIONAL_SECRET_ENV = ["LICENSE_API_SECRET"];

const RECOMMENDED_ENV = [
  "UPSTASH_REDIS_REST_URL",
  "UPSTASH_REDIS_REST_TOKEN",
  "RESEND_API_KEY",
  "EMAIL_FROM",
  "BACKUP_ENCRYPTION_KEY"
];

const SECRET_MIN_LENGTHS = {
  AUTH_SECRET: 32,
  LICENSE_HASH_SECRET: 32,
  LICENSE_KEY_ENCRYPTION_SECRET: 32,
  LICENSE_API_SECRET: 32,
  STRIPE_WEBHOOK_SECRET: 12
};

const ENV_FILES = [".env", ".env.local", ".env.production", ".env.production.local"];

const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "0.0.0.0", "::1"]);

const PLACEHOLDER_PATTERNS = [
  /dev-only/i,
  /change-me/i,
  /changeme/i,
  /replace-with/i,
  /shared-secret-used-by-the-desktop-software/i,
  /password123/i,
  /\.\.\./,
  /^test-/i,
  /^sk_test_/,
  /_test_/i
];

function parseDotEnv(content) {
  const values = {};

  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();

    if (!line || line.startsWith("#")) {
      continue;
    }

    const match = /^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/.exec(line);

    if (!match) {
      continue;
    }

    const [, key, rawValue] = match;
    values[key] = normalizeDotEnvValue(rawValue);
  }

  return values;
}

function normalizeDotEnvValue(rawValue) {
  const trimmed = rawValue.trim();
  const quote = trimmed[0];

  if ((quote === "\"" || quote === "'") && trimmed.endsWith(quote)) {
    const unquoted = trimmed.slice(1, -1);
    return quote === "\"" ? unquoted.replace(/\\n/g, "\n").replace(/\\"/g, "\"") : unquoted;
  }

  return trimmed.replace(/\s+#.*$/, "");
}

function loadDotEnvFiles(cwd = process.cwd()) {
  const loaded = {};
  const files = [];

  for (const fileName of ENV_FILES) {
    const filePath = path.join(cwd, fileName);

    if (!fs.existsSync(filePath)) {
      continue;
    }

    Object.assign(loaded, parseDotEnv(fs.readFileSync(filePath, "utf8")));
    files.push(fileName);
  }

  return { values: loaded, files };
}

function buildEnvironment(cwd = process.cwd()) {
  const loaded = loadDotEnvFiles(cwd);

  return {
    env: { ...loaded.values, ...process.env },
    files: loaded.files
  };
}

function validateProductionEnv(env) {
  const errors = [];
  const warnings = [];

  for (const name of REQUIRED_ENV) {
    if (!readEnv(env, name)) {
      errors.push(`${name} is required for production.`);
    }
  }

  validateUrl(errors, "DATABASE_URL", readEnv(env, "DATABASE_URL"), {
    protocols: ["postgres:", "postgresql:"],
    rejectLocalhost: true
  });
  validateUrl(errors, "APP_URL", readEnv(env, "APP_URL"), {
    protocols: ["https:"],
    rejectLocalhost: true,
    originOnly: true
  });
  validateSecretValues(errors, env);
  validateStripe(errors, env);
  validateTrustedOrigins(errors, env);
  validateRecommended(warnings, env);

  return { errors, warnings };
}

function readEnv(env, name) {
  return String(env[name] ?? "").trim();
}

function validateUrl(errors, name, value, options) {
  if (!value) {
    return;
  }

  let parsed;

  try {
    parsed = new URL(value);
  } catch {
    errors.push(`${name} must be a valid URL.`);
    return;
  }

  if (!options.protocols.includes(parsed.protocol)) {
    errors.push(`${name} must use ${options.protocols.join(" or ")} in production.`);
  }

  if (options.rejectLocalhost && isLocalHost(parsed.hostname)) {
    errors.push(`${name} must not point to localhost in production.`);
  }

  if (options.originOnly && parsed.origin !== value.replace(/\/$/, "")) {
    errors.push(`${name} must be an origin only, for example https://app.example.com.`);
  }
}

function validateSecretValues(errors, env) {
  for (const [name, minLength] of Object.entries(SECRET_MIN_LENGTHS)) {
    const value = readEnv(env, name);

    if (!value) {
      continue;
    }

    if (value.length < minLength) {
      errors.push(`${name} must be at least ${minLength} characters long.`);
    }
  }

  for (const name of [...REQUIRED_ENV, ...OPTIONAL_SECRET_ENV]) {
    const value = readEnv(env, name);

    if (value && looksLikeDevelopmentValue(value)) {
      errors.push(`${name} looks like a development, test, or placeholder value.`);
    }
  }

  if (readEnv(env, "LICENSE_HASH_SECRET") === readEnv(env, "LICENSE_KEY_ENCRYPTION_SECRET")) {
    errors.push("LICENSE_KEY_ENCRYPTION_SECRET must be distinct from LICENSE_HASH_SECRET.");
  }
}

function validateStripe(errors, env) {
  const stripeSecretKey = readEnv(env, "STRIPE_SECRET_KEY");
  const webhookSecret = readEnv(env, "STRIPE_WEBHOOK_SECRET");

  if (stripeSecretKey && !stripeSecretKey.startsWith("sk_live_")) {
    errors.push("STRIPE_SECRET_KEY must be a live key starting with sk_live_ in production.");
  }

  if (webhookSecret && !webhookSecret.startsWith("whsec_")) {
    errors.push("STRIPE_WEBHOOK_SECRET must start with whsec_.");
  }
}

function validateTrustedOrigins(errors, env) {
  const trustedOrigins = readEnv(env, "CSRF_TRUSTED_ORIGINS");

  if (!trustedOrigins) {
    return;
  }

  for (const origin of trustedOrigins.split(",").map((item) => item.trim()).filter(Boolean)) {
    validateUrl(errors, "CSRF_TRUSTED_ORIGINS", origin, {
      protocols: ["https:"],
      rejectLocalhost: true,
      originOnly: true
    });
  }
}

function validateRecommended(warnings, env) {
  for (const name of RECOMMENDED_ENV) {
    if (!readEnv(env, name)) {
      warnings.push(`${name} is recommended for production operations.`);
    }
  }

  const hasFallbackPrice = Boolean(readEnv(env, "STRIPE_PRICE_ID"));
  const hasProductPrices = ["STRIPE_ENDPOINT_PRICE_ID", "STRIPE_SERVER_PRICE_ID", "STRIPE_MOBILE_PRICE_ID"].every((name) =>
    Boolean(readEnv(env, name))
  );

  if (!hasFallbackPrice && !hasProductPrices) {
    warnings.push("Configure STRIPE_PRICE_ID or all product-specific Stripe price ids before enabling checkout.");
  }

  if (readEnv(env, "BACKUP_UPLOAD_ENABLED").toLowerCase() === "true" && !readEnv(env, "BACKUP_S3_BUCKET")) {
    warnings.push("BACKUP_UPLOAD_ENABLED is true but BACKUP_S3_BUCKET is missing.");
  }
}

function isLocalHost(hostname) {
  return LOCAL_HOSTS.has(hostname.toLowerCase());
}

function looksLikeDevelopmentValue(value) {
  return PLACEHOLDER_PATTERNS.some((pattern) => pattern.test(value));
}

function printResult({ errors, warnings }, files) {
  if (files.length) {
    console.log(`Loaded env files: ${files.join(", ")}`);
  } else {
    console.log("Loaded env files: none");
  }

  if (warnings.length) {
    console.warn("\nProduction preflight warnings:");
    for (const warning of warnings) {
      console.warn(`- ${warning}`);
    }
  }

  if (errors.length) {
    console.error("\nProduction preflight failed:");
    for (const error of errors) {
      console.error(`- ${error}`);
    }
    process.exitCode = 1;
    return;
  }

  console.log("\nProduction preflight passed.");
}

const invokedDirectly = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);

if (invokedDirectly) {
  const { env, files } = buildEnvironment();
  printResult(validateProductionEnv(env), files);
}

export { parseDotEnv, validateProductionEnv };
