-- An approved proposal may be claimed once. Failed runs require a new reviewed
-- proposal rather than replaying a partially executed command sequence.
CREATE UNIQUE INDEX IF NOT EXISTS remediation_runs_one_per_proposal
ON remediation_runs(proposal_id) WHERE proposal_id IS NOT NULL;
