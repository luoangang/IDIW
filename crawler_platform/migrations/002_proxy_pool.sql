CREATE TABLE IF NOT EXISTS proxy_endpoints (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(128) NOT NULL,
  proxy_url VARCHAR(512) CHARACTER SET ascii COLLATE ascii_bin NOT NULL UNIQUE,
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  last_selected_at DATETIME(6) NULL,
  selected_count BIGINT UNSIGNED NOT NULL DEFAULT 0,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  INDEX idx_proxy_selection (enabled, last_selected_at, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS proxy_run_assignments (
  package_run_id BIGINT UNSIGNED PRIMARY KEY,
  proxy_endpoint_id BIGINT UNSIGNED NOT NULL,
  assigned_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  CONSTRAINT fk_proxy_assignment_run FOREIGN KEY (package_run_id) REFERENCES package_runs(id) ON DELETE RESTRICT,
  CONSTRAINT fk_proxy_assignment_endpoint FOREIGN KEY (proxy_endpoint_id) REFERENCES proxy_endpoints(id) ON DELETE RESTRICT,
  INDEX idx_proxy_assignment_endpoint (proxy_endpoint_id, assigned_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
