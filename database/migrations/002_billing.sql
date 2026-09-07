-- ==================================================
-- Project Monitor - Billing Tables
-- Migration 002: Billing & Usage Tracking
-- ==================================================

-- 20. billing_invoices - Client invoices
CREATE TABLE billing_invoices (
    invoice_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    plan VARCHAR(50) NOT NULL DEFAULT 'starter',
    billing_cycle VARCHAR(20) NOT NULL DEFAULT 'monthly',
    amount NUMERIC(10,2) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    due_date TIMESTAMPTZ,
    paid_at TIMESTAMPTZ,
    payment_method VARCHAR(50),
    items JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 21. billing_usage - Usage tracking per client
CREATE TABLE billing_usage (
    record_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    metric VARCHAR(100) NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    recorded_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_billing_invoices_client ON billing_invoices(client_id);
CREATE INDEX idx_billing_invoices_status ON billing_invoices(status);
CREATE INDEX idx_billing_usage_client ON billing_usage(client_id);
CREATE INDEX idx_billing_usage_metric ON billing_usage(metric);
CREATE INDEX idx_billing_usage_recorded ON billing_usage(recorded_at);
