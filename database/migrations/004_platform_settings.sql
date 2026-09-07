-- Keep application preferences separate from n8n's historical settings table.
CREATE TABLE IF NOT EXISTS platform_settings (
    setting_key TEXT PRIMARY KEY,
    setting_value JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='settings' AND column_name='key') THEN
        INSERT INTO platform_settings (setting_key, setting_value)
        SELECT key, to_jsonb(value) FROM settings
        WHERE key IN ('profile.name', 'profile.company', 'notifications.telegram_enabled', 'security.session_timeout')
        ON CONFLICT DO NOTHING;
    ELSIF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='settings' AND column_name='setting_key') THEN
        INSERT INTO platform_settings (setting_key, setting_value)
        SELECT setting_key, setting_value FROM settings
        WHERE setting_key IN ('profile.name', 'profile.company', 'notifications.telegram_enabled', 'security.session_timeout')
        ON CONFLICT DO NOTHING;
    END IF;
END $$;
