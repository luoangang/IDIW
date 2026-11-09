ALTER TABLE monitors ADD COLUMN weekly_report_enabled TINYINT(1) NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS weekly_reports (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  monitor_id BIGINT UNSIGNED NOT NULL,
  week_start DATE NOT NULL,
  status VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'queued',
  attempts TINYINT UNSIGNED NOT NULL DEFAULT 0,
  available_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  source_count INT UNSIGNED NOT NULL DEFAULT 0,
  evidence_json JSON NULL,
  content_json JSON NULL,
  model VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  usage_json JSON NULL,
  error_message TEXT NULL,
  started_at DATETIME(6) NULL,
  finished_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  CONSTRAINT fk_weekly_reports_monitor FOREIGN KEY (monitor_id) REFERENCES monitors(id) ON DELETE RESTRICT,
  UNIQUE KEY uk_weekly_report_monitor_week (monitor_id, week_start),
  INDEX idx_weekly_reports_queue (status, available_at),
  INDEX idx_weekly_reports_recent (monitor_id, week_start)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
