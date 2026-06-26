import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { checkRateLimit, resetRateLimitForTests } from "@/lib/rate-limit";

const originalRedisUrl = process.env.UPSTASH_REDIS_REST_URL;
const originalRedisToken = process.env.UPSTASH_REDIS_REST_TOKEN;

type Bucket = {
  count: number;
  expiresAt: number;
};

const buckets = new Map<string, Bucket>();

function restoreEnv() {
  if (originalRedisUrl === undefined) {
    delete process.env.UPSTASH_REDIS_REST_URL;
  } else {
    process.env.UPSTASH_REDIS_REST_URL = originalRedisUrl;
  }

  if (originalRedisToken === undefined) {
    delete process.env.UPSTASH_REDIS_REST_TOKEN;
  } else {
    process.env.UPSTASH_REDIS_REST_TOKEN = originalRedisToken;
  }

}

function installUpstashMock() {
  process.env.UPSTASH_REDIS_REST_URL = "https://redis.example";
  process.env.UPSTASH_REDIS_REST_TOKEN = "redis-token";

  vi.stubGlobal(
    "fetch",
    vi.fn(async (_url: string, init?: RequestInit) => {
      const command = JSON.parse(String(init?.body)) as unknown[];
      const key = String(command[3]);
      const windowMs = Number(command[4]);
      const now = Date.now();
      const current = buckets.get(key);
      const next =
        !current || current.expiresAt <= now
          ? { count: 1, expiresAt: now + windowMs }
          : { count: current.count + 1, expiresAt: current.expiresAt };

      buckets.set(key, next);

      return Response.json({
        result: [next.count, next.expiresAt - now]
      });
    })
  );
}

describe("rate limiter", () => {
  beforeEach(() => {
    vi.stubEnv("NODE_ENV", "test");
    resetRateLimitForTests();
    buckets.clear();
    vi.unstubAllGlobals();
    installUpstashMock();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    restoreEnv();
  });

  it("blocks requests after the configured limit", async () => {
    expect(await checkRateLimit({ key: "login:1", limit: 2, windowMs: 10_000 })).toMatchObject({
      allowed: true,
      backend: "upstash"
    });
    expect((await checkRateLimit({ key: "login:1", limit: 2, windowMs: 10_000 })).allowed).toBe(true);
    expect(await checkRateLimit({ key: "login:1", limit: 2, windowMs: 10_000 })).toMatchObject({
      allowed: false,
      backend: "upstash"
    });
  });

  it("keeps independent buckets per key", async () => {
    expect((await checkRateLimit({ key: "license:a", limit: 1, windowMs: 10_000 })).allowed).toBe(true);
    expect((await checkRateLimit({ key: "license:b", limit: 1, windowMs: 10_000 })).allowed).toBe(true);
    expect((await checkRateLimit({ key: "license:a", limit: 1, windowMs: 10_000 })).allowed).toBe(false);
  });

  it("fails closed outside development when Redis is not configured", async () => {
    delete process.env.UPSTASH_REDIS_REST_URL;
    delete process.env.UPSTASH_REDIS_REST_TOKEN;

    const result = await checkRateLimit({ key: "login:1", limit: 2, windowMs: 10_000 });

    expect(result.allowed).toBe(false);
    expect(result.unavailable).toBe(true);
  });

  it("uses a local in-memory fallback only in development when Redis is not configured", async () => {
    vi.stubEnv("NODE_ENV", "development");
    delete process.env.UPSTASH_REDIS_REST_URL;
    delete process.env.UPSTASH_REDIS_REST_TOKEN;

    expect(await checkRateLimit({ key: "dev-login:1", limit: 2, windowMs: 10_000 })).toMatchObject({
      allowed: true,
      remaining: 1,
      backend: "memory"
    });
    expect((await checkRateLimit({ key: "dev-login:1", limit: 2, windowMs: 10_000 })).allowed).toBe(true);
    expect(await checkRateLimit({ key: "dev-login:1", limit: 2, windowMs: 10_000 })).toMatchObject({
      allowed: false,
      remaining: 0,
      backend: "memory"
    });
  });

  it("falls back to local memory in development when Upstash is unavailable", async () => {
    vi.stubEnv("NODE_ENV", "development");
    process.env.UPSTASH_REDIS_REST_URL = "https://redis.example";
    process.env.UPSTASH_REDIS_REST_TOKEN = "redis-token";
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ error: "temporary unavailable" }, { status: 503 }))
    );

    expect(await checkRateLimit({ key: "dev-checkout:1", limit: 1, windowMs: 10_000 })).toMatchObject({
      allowed: true,
      backend: "memory"
    });
    expect(await checkRateLimit({ key: "dev-checkout:1", limit: 1, windowMs: 10_000 })).toMatchObject({
      allowed: false,
      backend: "memory"
    });
  });

  it("fails closed in production when Upstash is unavailable", async () => {
    vi.stubEnv("NODE_ENV", "production");
    process.env.UPSTASH_REDIS_REST_URL = "https://redis.example";
    process.env.UPSTASH_REDIS_REST_TOKEN = "redis-token";
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ error: "temporary unavailable" }, { status: 503 }))
    );

    const result = await checkRateLimit({ key: "prod-checkout:1", limit: 1, windowMs: 10_000 });

    expect(result.allowed).toBe(false);
    expect(result.unavailable).toBe(true);
    expect(result.backend).toBeUndefined();
  });
});
