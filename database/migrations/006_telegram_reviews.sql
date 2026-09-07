CREATE TABLE IF NOT EXISTS incident_reviews (
    review_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_id UUID NOT NULL UNIQUE REFERENCES incidents(incident_id) ON DELETE CASCADE,
    proposal_id UUID REFERENCES fix_proposals(proposal_id),
    approval_id UUID REFERENCES approvals(approval_id),
    state TEXT NOT NULL DEFAULT 'NEW',
    snapshot_hash TEXT,
    review_document JSONB,
    message_id BIGINT,
    chat_id TEXT,
    actor_id TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW()+INTERVAL '24 hours',
    last_error TEXT,
    result_text TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS incident_reviews_pending ON incident_reviews(state,next_attempt_at);
