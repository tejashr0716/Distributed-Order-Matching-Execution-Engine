-- ApexMatch Distributed Order Matching & Execution Engine Schema
-- PostgreSQL / Azure SQL Compatible

DROP TABLE IF EXISTS clearing_settlements CASCADE;
DROP TABLE IF EXISTS trades CASCADE;
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS trader_accounts CASCADE;
DROP TABLE IF EXISTS instruments CASCADE;
DROP TABLE IF EXISTS market_depth_snapshots CASCADE;

CREATE TABLE instruments (
    symbol VARCHAR(32) PRIMARY KEY,
    base_asset VARCHAR(16) NOT NULL,
    quote_asset VARCHAR(16) NOT NULL,
    tick_size NUMERIC(18, 8) DEFAULT 0.01,
    min_order_size NUMERIC(18, 8) DEFAULT 0.0001,
    status VARCHAR(16) DEFAULT 'ACTIVE'
);

CREATE TABLE trader_accounts (
    account_id VARCHAR(64) PRIMARY KEY,
    username VARCHAR(64) NOT NULL,
    fiat_balance NUMERIC(18, 4) DEFAULT 100000.0000,
    asset_balance NUMERIC(18, 8) DEFAULT 10.00000000,
    locked_fiat NUMERIC(18, 4) DEFAULT 0.0000,
    locked_asset NUMERIC(18, 8) DEFAULT 0.00000000,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    client_id VARCHAR(64) NOT NULL,
    symbol VARCHAR(32) NOT NULL REFERENCES instruments(symbol),
    side VARCHAR(8) NOT NULL,
    type VARCHAR(16) NOT NULL,
    tif VARCHAR(16) NOT NULL,
    price NUMERIC(18, 4) NOT NULL,
    quantity NUMERIC(18, 8) NOT NULL,
    filled_quantity NUMERIC(18, 8) DEFAULT 0.00000000,
    remaining_quantity NUMERIC(18, 8) NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_orders_client ON orders(client_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_symbol ON orders(symbol);

CREATE TABLE trades (
    match_id BIGINT PRIMARY KEY,
    symbol VARCHAR(32) NOT NULL REFERENCES instruments(symbol),
    buyer_order_id BIGINT NOT NULL,
    seller_order_id BIGINT NOT NULL,
    buyer_client_id VARCHAR(64) NOT NULL,
    seller_client_id VARCHAR(64) NOT NULL,
    price NUMERIC(18, 4) NOT NULL,
    quantity NUMERIC(18, 8) NOT NULL,
    quote_amount NUMERIC(18, 4) NOT NULL,
    taker_side VARCHAR(8) NOT NULL,
    latency_ns BIGINT NOT NULL,
    executed_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_trades_symbol_time ON trades(symbol, executed_at DESC);
CREATE INDEX idx_trades_buyer ON trades(buyer_client_id);
CREATE INDEX idx_trades_seller ON trades(seller_client_id);

CREATE TABLE clearing_settlements (
    settlement_id BIGSERIAL PRIMARY KEY,
    match_id BIGINT NOT NULL REFERENCES trades(match_id),
    buyer_account_id VARCHAR(64) NOT NULL,
    seller_account_id VARCHAR(64) NOT NULL,
    settled_fiat NUMERIC(18, 4) NOT NULL,
    settled_asset NUMERIC(18, 8) NOT NULL,
    clearing_fee NUMERIC(18, 4) DEFAULT 0.0000,
    settlement_status VARCHAR(16) DEFAULT 'SETTLED',
    settled_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE market_depth_snapshots (
    snapshot_id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(32) NOT NULL,
    mid_price NUMERIC(18, 4) NOT NULL,
    spread NUMERIC(18, 4) NOT NULL,
    bid_levels JSONB NOT NULL,
    ask_levels JSONB NOT NULL,
    captured_at TIMESTAMPTZ DEFAULT NOW()
);

-- Seed Initial Instrument & Demo Accounts
INSERT INTO instruments (symbol, base_asset, quote_asset, tick_size, min_order_size, status)
VALUES 
    ('BTC-USD', 'BTC', 'USD', 0.50, 0.001, 'ACTIVE'),
    ('ETH-USD', 'ETH', 'USD', 0.10, 0.01, 'ACTIVE')
ON CONFLICT (symbol) DO NOTHING;

INSERT INTO trader_accounts (account_id, username, fiat_balance, asset_balance)
VALUES 
    ('MM_BOT_01', 'HighFreqMarketMaker', 5000000.0000, 150.00000000),
    ('WHALE_01', 'CryptoWhaleAlpha', 10000000.0000, 300.00000000),
    ('TRADER_ALICE', 'Alice_Quant', 250000.0000, 8.50000000),
    ('TRADER_BOB', 'Bob_Scalper', 150000.0000, 4.25000000)
ON CONFLICT (account_id) DO NOTHING;
