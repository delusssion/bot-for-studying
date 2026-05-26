import asyncpg

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id              BIGINT PRIMARY KEY,
    username             TEXT,
    full_name            TEXT,
    balance              INTEGER NOT NULL DEFAULT 0,
    subscription_until   TIMESTAMP NULL,
    referral_id          BIGINT NULL REFERENCES users(user_id),
    free_edit_used_total INTEGER NOT NULL DEFAULT 0,
    agreed               BOOLEAN NOT NULL DEFAULT FALSE,
    trial_used           BOOLEAN NOT NULL DEFAULT FALSE,
    created_at           TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS orders (
    id              SERIAL PRIMARY KEY,
    user_id         BIGINT NOT NULL REFERENCES users(user_id),
    type            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    input_data      JSONB,
    result_json     JSONB,
    result_file_id  TEXT NULL,
    tokens_input    INTEGER,
    tokens_output   INTEGER,
    cost_kopecks    INTEGER,
    price_kopecks   INTEGER,
    free_edit_used  BOOLEAN NOT NULL DEFAULT FALSE,
    edit_count      INTEGER NOT NULL DEFAULT 0,
    is_trial        BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS payments (
    id              SERIAL PRIMARY KEY,
    user_id         BIGINT NOT NULL REFERENCES users(user_id),
    amount_kopecks  INTEGER NOT NULL,
    type            TEXT NOT NULL,
    external_id     TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS edits (
    id               SERIAL PRIMARY KEY,
    order_id         INTEGER NOT NULL REFERENCES orders(id),
    user_id          BIGINT NOT NULL REFERENCES users(user_id),
    edit_type        TEXT NOT NULL,
    edit_instruction TEXT,
    tokens_used      INTEGER,
    is_paid          BOOLEAN NOT NULL DEFAULT FALSE,
    price_kopecks    INTEGER NOT NULL DEFAULT 0,
    created_at       TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS referral_codes (
    id         SERIAL PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES users(user_id) UNIQUE,
    code       TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS referral_uses (
    id                 SERIAL PRIMARY KEY,
    inviter_id         BIGINT NOT NULL REFERENCES users(user_id),
    invitee_id         BIGINT NOT NULL REFERENCES users(user_id) UNIQUE,
    code               TEXT NOT NULL,
    bonus_invitee_paid BOOLEAN NOT NULL DEFAULT FALSE,
    bonus_inviter_paid BOOLEAN NOT NULL DEFAULT FALSE,
    created_at         TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS vip_usage (
    id             SERIAL PRIMARY KEY,
    user_id        BIGINT REFERENCES users(user_id),
    date           DATE DEFAULT CURRENT_DATE,
    requests_used  INTEGER DEFAULT 0,
    UNIQUE(user_id, date)
);

CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TIMESTAMP DEFAULT NOW()
);
"""

SETTINGS_SEED_SQL = """
INSERT INTO settings (key, value) VALUES
    ('price_lab_docx',      '15000'),
    ('price_presentation',  '18000'),
    ('price_lab_plus_pres', '28000'),
    ('price_text_answer',   '2000'),
    ('price_subscription',  '99900'),
    ('price_extra_edit',    '1500'),
    ('vip_daily_limit',     '3'),
    ('maintenance_mode',    'false')
ON CONFLICT (key) DO NOTHING;
"""

# Migrations for existing databases
MIGRATIONS_SQL = """
UPDATE settings SET value = '25000' WHERE key = 'price_presentation';
ALTER TABLE users ADD COLUMN IF NOT EXISTS agreed BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_used BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS is_trial BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_vip BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS vip_daily_limit INTEGER DEFAULT 3;
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_blocked BOOLEAN DEFAULT FALSE;
ALTER TABLE payments DROP COLUMN IF EXISTS payment_code;
ALTER TABLE payments DROP COLUMN IF EXISTS expires_at;
ALTER TABLE payments ADD COLUMN IF NOT EXISTS paid_at TIMESTAMP;
"""


async def create_tables(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(CREATE_TABLES_SQL)
        await conn.execute(MIGRATIONS_SQL)
        await conn.execute(SETTINGS_SEED_SQL)
