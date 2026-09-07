CREATE TABLE IF NOT EXISTS log_cursors (
    project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    cursor_data JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(project_id,file_path)
);
