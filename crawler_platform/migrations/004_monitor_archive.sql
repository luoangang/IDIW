ALTER TABLE monitors
  ADD COLUMN archived_at DATETIME(6) NULL,
  ADD COLUMN active_name_key CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL;

CREATE UNIQUE INDEX uk_monitors_active_name ON monitors(active_name_key);
