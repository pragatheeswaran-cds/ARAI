-- ARAI metadata schema, version 15 (decision AM-77): when a person last looked at their notifications. Notifications
-- themselves are not stored: they are read from the reviews and the runs, and this timestamp tells which are new.

ALTER TABLE users ADD COLUMN notifications_seen_at TIMESTAMPTZ;
