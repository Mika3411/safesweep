-- SafeSweep License Portal - PostgreSQL schema
-- Tables: users, products, licenses, license_activations, orders,
-- subscriptions, invoices, license_validation_logs.

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;

CREATE TYPE user_role AS ENUM ('customer', 'admin', 'support');
CREATE TYPE license_status AS ENUM ('active', 'expired', 'suspended', 'revoked');
CREATE TYPE order_status AS ENUM ('pending', 'paid', 'cancelled', 'refunded', 'failed');
CREATE TYPE subscription_status AS ENUM (
  'trialing',
  'active',
  'past_due',
  'paused',
  'cancelled',
  'expired'
);
CREATE TYPE invoice_status AS ENUM ('draft', 'open', 'paid', 'void', 'uncollectible');
CREATE TYPE validation_result AS ENUM ('allowed', 'denied');
CREATE TYPE validation_reason AS ENUM (
  'valid',
  'license_not_found',
  'license_expired',
  'license_suspended',
  'license_revoked',
  'activation_created',
  'activation_limit_reached',
  'device_deactivated',
  'invalid_request',
  'rate_limited'
);

CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email CITEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  full_name TEXT NOT NULL,
  company_name TEXT,
  role user_role NOT NULL DEFAULT 'customer',
  stripe_customer_id TEXT UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE products (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  sku TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  version TEXT,
  description TEXT,
  default_max_activations INTEGER NOT NULL DEFAULT 1 CHECK (default_max_activations > 0),
  price_cents INTEGER NOT NULL DEFAULT 0 CHECK (price_cents >= 0),
  currency CHAR(3) NOT NULL DEFAULT 'EUR',
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE licenses (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  product_id UUID NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
  license_key_hash TEXT NOT NULL UNIQUE,
  status license_status NOT NULL DEFAULT 'active',
  expires_at TIMESTAMPTZ,
  max_activations INTEGER NOT NULL DEFAULT 1 CHECK (max_activations > 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE license_activations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  license_id UUID NOT NULL REFERENCES licenses(id) ON DELETE CASCADE,
  device_id TEXT NOT NULL,
  device_name TEXT NOT NULL,
  ip_address INET NOT NULL,
  activated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deactivated_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (license_id, device_id),
  CHECK (last_seen_at >= activated_at)
);

CREATE TABLE orders (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  product_id UUID NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
  license_id UUID REFERENCES licenses(id) ON DELETE SET NULL,
  stripe_checkout_session_id TEXT UNIQUE,
  status order_status NOT NULL DEFAULT 'pending',
  quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
  amount_cents INTEGER NOT NULL CHECK (amount_cents >= 0),
  currency CHAR(3) NOT NULL DEFAULT 'EUR',
  ordered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  paid_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE subscriptions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  product_id UUID NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
  license_id UUID NOT NULL REFERENCES licenses(id) ON DELETE CASCADE,
  stripe_subscription_id TEXT UNIQUE,
  status subscription_status NOT NULL DEFAULT 'active',
  current_period_start TIMESTAMPTZ NOT NULL,
  current_period_end TIMESTAMPTZ NOT NULL,
  cancel_at_period_end BOOLEAN NOT NULL DEFAULT false,
  cancelled_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (current_period_end > current_period_start)
);

CREATE TABLE invoices (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  order_id UUID REFERENCES orders(id) ON DELETE SET NULL,
  subscription_id UUID REFERENCES subscriptions(id) ON DELETE SET NULL,
  stripe_invoice_id TEXT UNIQUE,
  invoice_number TEXT NOT NULL,
  status invoice_status NOT NULL DEFAULT 'open',
  amount_due_cents INTEGER NOT NULL CHECK (amount_due_cents >= 0),
  amount_paid_cents INTEGER NOT NULL DEFAULT 0 CHECK (amount_paid_cents >= 0),
  currency CHAR(3) NOT NULL DEFAULT 'EUR',
  hosted_invoice_url TEXT,
  invoice_pdf_url TEXT,
  issued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  due_at TIMESTAMPTZ,
  paid_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE license_validation_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  license_id UUID REFERENCES licenses(id) ON DELETE SET NULL,
  activation_id UUID REFERENCES license_activations(id) ON DELETE SET NULL,
  license_key_hash TEXT,
  device_id TEXT,
  device_name TEXT,
  ip_address INET,
  result validation_result NOT NULL,
  reason validation_reason NOT NULL,
  user_agent TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  validated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- updated_at trigger shared by all mutable tables.
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER users_set_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER products_set_updated_at
BEFORE UPDATE ON products
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER licenses_set_updated_at
BEFORE UPDATE ON licenses
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER license_activations_set_updated_at
BEFORE UPDATE ON license_activations
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER orders_set_updated_at
BEFORE UPDATE ON orders
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER subscriptions_set_updated_at
BEFORE UPDATE ON subscriptions
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER invoices_set_updated_at
BEFORE UPDATE ON invoices
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Indexes for common access paths.
CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_products_active ON products(is_active);

CREATE INDEX idx_licenses_user_id ON licenses(user_id);
CREATE INDEX idx_licenses_product_id ON licenses(product_id);
CREATE INDEX idx_licenses_status ON licenses(status);
CREATE INDEX idx_licenses_expires_at ON licenses(expires_at);
CREATE INDEX idx_licenses_user_status ON licenses(user_id, status);

CREATE INDEX idx_license_activations_license_id ON license_activations(license_id);
CREATE INDEX idx_license_activations_last_seen_at ON license_activations(last_seen_at);
CREATE INDEX idx_license_activations_active
  ON license_activations(license_id)
  WHERE deactivated_at IS NULL;

CREATE INDEX idx_orders_user_id ON orders(user_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_paid_at ON orders(paid_at);

CREATE INDEX idx_subscriptions_user_id ON subscriptions(user_id);
CREATE INDEX idx_subscriptions_license_id ON subscriptions(license_id);
CREATE INDEX idx_subscriptions_status ON subscriptions(status);
CREATE INDEX idx_subscriptions_period_end ON subscriptions(current_period_end);

CREATE INDEX idx_invoices_user_id ON invoices(user_id);
CREATE INDEX idx_invoices_status ON invoices(status);
CREATE INDEX idx_invoices_issued_at ON invoices(issued_at);

CREATE INDEX idx_validation_logs_license_id ON license_validation_logs(license_id);
CREATE INDEX idx_validation_logs_device_id ON license_validation_logs(device_id);
CREATE INDEX idx_validation_logs_result ON license_validation_logs(result);
CREATE INDEX idx_validation_logs_validated_at ON license_validation_logs(validated_at);
CREATE INDEX idx_validation_logs_metadata_gin ON license_validation_logs USING GIN(metadata);

-- Optional: expire active licenses automatically from a scheduled job.
-- UPDATE licenses
-- SET status = 'expired'
-- WHERE status = 'active'
--   AND expires_at IS NOT NULL
--   AND expires_at < now();

-- Example queries ---------------------------------------------------------

-- 1. Create a product.
INSERT INTO products (sku, name, version, default_max_activations, price_cents)
VALUES ('SS-ENDPOINT', 'SafeSweep Endpoint', '1.0', 3, 9900);

-- 2. Create a user.
INSERT INTO users (email, password_hash, full_name, company_name)
VALUES ('client@example.com', '$2b$12$replace_with_bcrypt_hash', 'Camille Martin', 'Acme Industries');

-- 3. Create a license.
-- license_key_hash must be produced in application code with HMAC/SHA-256 or equivalent.
INSERT INTO licenses (
  user_id,
  product_id,
  license_key_hash,
  status,
  expires_at,
  max_activations
)
SELECT
  u.id,
  p.id,
  'sha256_or_hmac_hash_of_license_key',
  'active',
  now() + interval '1 year',
  p.default_max_activations
FROM users u
JOIN products p ON p.sku = 'SS-ENDPOINT'
WHERE u.email = 'client@example.com';

-- 4. List licenses for a customer with activation counts.
SELECT
  l.id,
  p.name AS product_name,
  l.status,
  l.expires_at,
  l.max_activations,
  count(a.id) FILTER (WHERE a.deactivated_at IS NULL) AS active_activations
FROM licenses l
JOIN products p ON p.id = l.product_id
LEFT JOIN license_activations a ON a.license_id = l.id
WHERE l.user_id = (
  SELECT id FROM users WHERE email = 'client@example.com'
)
GROUP BY l.id, p.name
ORDER BY l.created_at DESC;

-- 5. Validate a license by hash.
SELECT
  l.id,
  l.status,
  l.expires_at,
  l.max_activations,
  count(a.id) FILTER (WHERE a.deactivated_at IS NULL) AS active_activations,
  bool_or(a.device_id = 'DEVICE-123' AND a.deactivated_at IS NULL) AS device_already_active
FROM licenses l
LEFT JOIN license_activations a ON a.license_id = l.id
WHERE l.license_key_hash = 'sha256_or_hmac_hash_of_license_key'
GROUP BY l.id;

-- 6. Activate a device only if the license is usable and under the activation limit.
WITH selected_license AS (
  SELECT l.*
  FROM licenses l
  WHERE l.license_key_hash = 'sha256_or_hmac_hash_of_license_key'
    AND l.status = 'active'
    AND (l.expires_at IS NULL OR l.expires_at > now())
),
activation_count AS (
  SELECT
    sl.id AS license_id,
    count(a.id) FILTER (WHERE a.deactivated_at IS NULL) AS active_count,
    sl.max_activations
  FROM selected_license sl
  LEFT JOIN license_activations a ON a.license_id = sl.id
  GROUP BY sl.id, sl.max_activations
)
INSERT INTO license_activations (
  license_id,
  device_id,
  device_name,
  ip_address
)
SELECT
  license_id,
  'DEVICE-123',
  'Camille Laptop',
  '203.0.113.10'::inet
FROM activation_count
WHERE active_count < max_activations
ON CONFLICT (license_id, device_id)
DO UPDATE SET
  device_name = EXCLUDED.device_name,
  ip_address = EXCLUDED.ip_address,
  last_seen_at = now(),
  deactivated_at = NULL
RETURNING *;

-- 7. Log a validation decision.
INSERT INTO license_validation_logs (
  license_id,
  activation_id,
  license_key_hash,
  device_id,
  device_name,
  ip_address,
  result,
  reason,
  user_agent,
  metadata
)
VALUES (
  '00000000-0000-0000-0000-000000000000',
  NULL,
  'sha256_or_hmac_hash_of_license_key',
  'DEVICE-123',
  'Camille Laptop',
  '203.0.113.10'::inet,
  'allowed',
  'valid',
  'SafeSweep/1.0 Windows',
  '{"app_version":"1.0.0"}'
);

-- 8. Deactivate one device.
UPDATE license_activations
SET deactivated_at = now()
WHERE license_id = '00000000-0000-0000-0000-000000000000'
  AND device_id = 'DEVICE-123'
  AND deactivated_at IS NULL;

-- 9. Admin report: licenses expiring in the next 30 days.
SELECT
  u.email,
  u.company_name,
  p.name AS product_name,
  l.id AS license_id,
  l.status,
  l.expires_at
FROM licenses l
JOIN users u ON u.id = l.user_id
JOIN products p ON p.id = l.product_id
WHERE l.status = 'active'
  AND l.expires_at BETWEEN now() AND now() + interval '30 days'
ORDER BY l.expires_at ASC;

-- 10. Admin report: recent denied validations.
SELECT
  v.validated_at,
  v.reason,
  v.device_id,
  v.ip_address,
  u.email,
  p.name AS product_name
FROM license_validation_logs v
LEFT JOIN licenses l ON l.id = v.license_id
LEFT JOIN users u ON u.id = l.user_id
LEFT JOIN products p ON p.id = l.product_id
WHERE v.result = 'denied'
ORDER BY v.validated_at DESC
LIMIT 100;
