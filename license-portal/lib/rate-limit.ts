export type RateLimitOptions = {
  key: string;
  limit: number;
  windowMs: number;
};

export type RateLimitResult = {
  allowed: boolean;
  remaining: number;
  resetAt: number;
  unavailable?: boolean;
  backend?: "upstash" | "memory";
};

type UpstashResponse = {
  result?: unknown;
  error?: string;
};

type LocalBucket = {
  count: number;
  resetAt: number;
};

const RATE_LIMIT_SCRIPT = `
local current = redis.call("INCR", KEYS[1])
if current == 1 then
  redis.call("PEXPIRE", KEYS[1], ARGV[1])
end
local ttl = redis.call("PTTL", KEYS[1])
return { current, ttl }
`;

const localBuckets = new Map<string, LocalBucket>();

function unavailable(windowMs: number): RateLimitResult {
  return {
    allowed: false,
    remaining: 0,
    resetAt: Date.now() + windowMs,
    unavailable: true
  };
}

function isDevelopment() {
  return process.env.NODE_ENV === "development";
}

function allowsMemoryFallback() {
  return process.env.RATE_LIMIT_MEMORY_FALLBACK === "true";
}

function getUpstashConfig() {
  const url = process.env.UPSTASH_REDIS_REST_URL?.replace(/\/$/, "");
  const token = process.env.UPSTASH_REDIS_REST_TOKEN;

  if (!url || !token) {
    return null;
  }

  return { url, token };
}

function parseRedisResult(result: unknown) {
  if (!Array.isArray(result) || result.length < 2) {
    return null;
  }

  const count = Number(result[0]);
  const ttl = Number(result[1]);

  if (!Number.isFinite(count) || !Number.isFinite(ttl)) {
    return null;
  }

  return { count, ttl };
}

function checkLocalRateLimit({ key, limit, windowMs }: RateLimitOptions): RateLimitResult {
  const now = Date.now();
  const bucketKey = `rate-limit:${key}`;
  const current = localBuckets.get(bucketKey);
  const next =
    !current || current.resetAt <= now
      ? { count: 1, resetAt: now + windowMs }
      : { count: current.count + 1, resetAt: current.resetAt };

  localBuckets.set(bucketKey, next);

  return {
    allowed: next.count <= limit,
    remaining: Math.max(limit - next.count, 0),
    resetAt: next.resetAt,
    backend: "memory"
  };
}

function fallbackOrUnavailable(options: RateLimitOptions): RateLimitResult {
  return isDevelopment() || allowsMemoryFallback() ? checkLocalRateLimit(options) : unavailable(options.windowMs);
}

export async function checkRateLimit({ key, limit, windowMs }: RateLimitOptions): Promise<RateLimitResult> {
  const config = getUpstashConfig();
  const options = { key, limit, windowMs };

  if (!config) {
    return fallbackOrUnavailable(options);
  }

  try {
    const response = await fetch(config.url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${config.token}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify(["EVAL", RATE_LIMIT_SCRIPT, "1", `rate-limit:${key}`, String(windowMs)])
    });

    if (!response.ok) {
      return fallbackOrUnavailable(options);
    }

    const data = (await response.json()) as UpstashResponse;

    if (data.error) {
      return fallbackOrUnavailable(options);
    }

    const result = parseRedisResult(data.result);

    if (!result) {
      return fallbackOrUnavailable(options);
    }

    const ttl = result.ttl > 0 ? result.ttl : windowMs;

    return {
      allowed: result.count <= limit,
      remaining: Math.max(limit - result.count, 0),
      resetAt: Date.now() + ttl,
      backend: "upstash"
    };
  } catch {
    return fallbackOrUnavailable(options);
  }
}

export function resetRateLimitForTests() {
  localBuckets.clear();
}
