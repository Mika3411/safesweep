import { NextRequest } from "next/server";
import { afterEach, describe, expect, it } from "vitest";
import { getClientIp, requireSameOrigin } from "@/lib/http";

const originalTrustedProxyIps = process.env.TRUSTED_PROXY_IPS;
const originalAppUrl = process.env.APP_URL;
const originalCsrfTrustedOrigins = process.env.CSRF_TRUSTED_ORIGINS;

function restoreEnv() {
  if (originalTrustedProxyIps === undefined) {
    delete process.env.TRUSTED_PROXY_IPS;
  } else {
    process.env.TRUSTED_PROXY_IPS = originalTrustedProxyIps;
  }

  if (originalAppUrl === undefined) {
    delete process.env.APP_URL;
  } else {
    process.env.APP_URL = originalAppUrl;
  }

  if (originalCsrfTrustedOrigins === undefined) {
    delete process.env.CSRF_TRUSTED_ORIGINS;
  } else {
    process.env.CSRF_TRUSTED_ORIGINS = originalCsrfTrustedOrigins;
  }
}

function request(headers: Record<string, string>, directIp?: string) {
  const nextRequest = new NextRequest("http://localhost/test", { headers });

  if (directIp) {
    Object.defineProperty(nextRequest, "ip", { value: directIp });
  }

  return nextRequest;
}

describe("client IP resolution", () => {
  afterEach(() => {
    restoreEnv();
  });

  it("ignores forwarded headers when the direct peer is not trusted", () => {
    process.env.TRUSTED_PROXY_IPS = "10.0.0.1";

    expect(getClientIp(request({ "x-forwarded-for": "203.0.113.10" }, "198.51.100.5"))).toBe("198.51.100.5");
  });

  it("uses the forwarded client IP behind a trusted proxy", () => {
    process.env.TRUSTED_PROXY_IPS = "10.0.0.1";

    expect(getClientIp(request({ "x-forwarded-for": "198.51.100.8, 203.0.113.10" }, "10.0.0.1"))).toBe(
      "203.0.113.10"
    );
  });

  it("supports trusted proxy CIDR ranges", () => {
    process.env.TRUSTED_PROXY_IPS = "10.0.0.0/8";

    expect(getClientIp(request({ "x-real-ip": "198.51.100.9" }, "10.12.0.3"))).toBe("198.51.100.9");
  });

  it("returns unknown when no direct IP is available", () => {
    process.env.TRUSTED_PROXY_IPS = "10.0.0.0/8";

    expect(getClientIp(request({ "x-forwarded-for": "198.51.100.9" }))).toBe("unknown");
  });

  it("accepts same-origin mutations", () => {
    process.env.APP_URL = "https://portal.example";

    expect(requireSameOrigin(request({ origin: "https://portal.example", host: "portal.example" }))).toBeNull();
  });

  it("rejects missing or cross-site origins", async () => {
    process.env.APP_URL = "https://portal.example";

    const missingOrigin = requireSameOrigin(request({ host: "portal.example" }));
    const crossSite = requireSameOrigin(request({ origin: "https://attacker.example", host: "portal.example" }));

    expect(missingOrigin?.status).toBe(403);
    expect(crossSite?.status).toBe(403);
    await expect(crossSite?.json()).resolves.toMatchObject({ error: "Origin non autorisee." });
  });

  it("rejects trusted origins sent to an untrusted host", async () => {
    process.env.APP_URL = "https://portal.example";

    const response = requireSameOrigin(request({ origin: "https://portal.example", host: "attacker.example" }));

    expect(response?.status).toBe(403);
    await expect(response?.json()).resolves.toMatchObject({ error: "Host non autorise." });
  });

  it("accepts configured CSRF trusted origins", () => {
    process.env.APP_URL = "https://portal.example";
    process.env.CSRF_TRUSTED_ORIGINS = "https://preview.example, https://alias.example";

    expect(requireSameOrigin(request({ origin: "https://preview.example", host: "preview.example" }))).toBeNull();
  });
});
