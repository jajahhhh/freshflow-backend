-- Generated MySQL 8.4 reference schema. Python CLI init-db creates the same tables.
-- All event timestamps are UTC; business dates are store-local.
SET NAMES utf8mb4;


CREATE TABLE import_attempts (
	attempt_id INTEGER NOT NULL AUTO_INCREMENT, 
	file_name VARCHAR(255) NOT NULL, 
	checksum VARCHAR(64) NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	error VARCHAR(2000), 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (attempt_id)
);

CREATE TABLE import_jobs (
	import_id INTEGER NOT NULL AUTO_INCREMENT, 
	file_name VARCHAR(255) NOT NULL, 
	checksum VARCHAR(64) NOT NULL, 
	total_rows INTEGER NOT NULL, 
	inserted_rows INTEGER NOT NULL, 
	unchanged_rows INTEGER NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	imported_at DATETIME NOT NULL, 
	PRIMARY KEY (import_id), 
	UNIQUE (checksum)
);

CREATE TABLE products (
	product_id VARCHAR(40) NOT NULL, 
	product_name VARCHAR(200), 
	category VARCHAR(100), 
	regular_price NUMERIC(12, 2), 
	barcode VARCHAR(64), 
	PRIMARY KEY (product_id), 
	CONSTRAINT ck_product_price CHECK (regular_price >= 0), 
	UNIQUE (barcode)
);

CREATE TABLE stores (
	store_id VARCHAR(40) NOT NULL, 
	store_name VARCHAR(150), 
	latitude NUMERIC(9, 6), 
	longitude NUMERIC(9, 6), 
	timezone VARCHAR(60) NOT NULL, 
	PRIMARY KEY (store_id)
);

CREATE TABLE demand_predictions (
	prediction_id INTEGER NOT NULL AUTO_INCREMENT, 
	request_id VARCHAR(100) NOT NULL, 
	store_id VARCHAR(40) NOT NULL, 
	product_id VARCHAR(40) NOT NULL, 
	target_date DATE NOT NULL, 
	predicted_units NUMERIC(18, 6) NOT NULL, 
	prediction_kind VARCHAR(50) NOT NULL, 
	model_version VARCHAR(100) NOT NULL, 
	source VARCHAR(30) NOT NULL, 
	contains_weather_effect BOOL NOT NULL, 
	generated_at DATETIME NOT NULL, 
	input_cutoff_at DATETIME, 
	request_payload JSON NOT NULL, 
	PRIMARY KEY (prediction_id), 
	CONSTRAINT ck_prediction CHECK (predicted_units >= 0), 
	UNIQUE (request_id), 
	FOREIGN KEY(store_id) REFERENCES stores (store_id), 
	FOREIGN KEY(product_id) REFERENCES products (product_id)
);

CREATE INDEX ix_forecast ON demand_predictions (store_id, product_id, target_date, source);

CREATE TABLE inventory_snapshots (
	snapshot_id INTEGER NOT NULL AUTO_INCREMENT, 
	snapshot_date DATE NOT NULL, 
	store_id VARCHAR(40) NOT NULL, 
	product_id VARCHAR(40) NOT NULL, 
	opening_inventory_units INTEGER NOT NULL, 
	days_to_expiry INTEGER NOT NULL, 
	standard_shelf_life_days INTEGER NOT NULL, 
	delivery_lead_time_days INTEGER NOT NULL, 
	snapshot_source VARCHAR(100) NOT NULL, 
	import_id INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (snapshot_id), 
	CONSTRAINT uq_snapshot UNIQUE (snapshot_date, store_id, product_id), 
	CONSTRAINT ck_stock CHECK (opening_inventory_units >= 0), 
	CONSTRAINT ck_shelf CHECK (standard_shelf_life_days > 0), 
	CONSTRAINT ck_lead CHECK (delivery_lead_time_days >= 0), 
	FOREIGN KEY(store_id) REFERENCES stores (store_id), 
	FOREIGN KEY(product_id) REFERENCES products (product_id), 
	FOREIGN KEY(import_id) REFERENCES import_jobs (import_id)
);

CREATE INDEX ix_expiring ON inventory_snapshots (snapshot_date, store_id, days_to_expiry);

CREATE TABLE recommendation_runs (
	run_id INTEGER NOT NULL AUTO_INCREMENT, 
	request_id VARCHAR(100) NOT NULL, 
	snapshot_date DATE NOT NULL, 
	store_id VARCHAR(40) NOT NULL, 
	scenario_id VARCHAR(100) NOT NULL, 
	rule_version VARCHAR(100) NOT NULL, 
	prediction_source VARCHAR(30) NOT NULL, 
	total_items INTEGER NOT NULL, 
	ready_count INTEGER NOT NULL, 
	not_ready_count INTEGER NOT NULL, 
	review_count INTEGER NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	request_payload JSON NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (run_id), 
	UNIQUE (request_id), 
	FOREIGN KEY(store_id) REFERENCES stores (store_id)
);

CREATE TABLE weather_inputs (
	weather_id INTEGER NOT NULL AUTO_INCREMENT, 
	request_id VARCHAR(100) NOT NULL, 
	scenario_id VARCHAR(100) NOT NULL, 
	store_id VARCHAR(40) NOT NULL, 
	target_date DATE NOT NULL, 
	`condition` VARCHAR(30) NOT NULL, 
	temperature_c NUMERIC(7, 3), 
	rain_mm_1h NUMERIC(12, 3), 
	source VARCHAR(30) NOT NULL, 
	is_mock BOOL NOT NULL, 
	fetched_at DATETIME NOT NULL, 
	raw_payload JSON NOT NULL, 
	PRIMARY KEY (weather_id), 
	CONSTRAINT uq_weather_scenario UNIQUE (scenario_id, store_id, target_date), 
	UNIQUE (request_id), 
	FOREIGN KEY(store_id) REFERENCES stores (store_id)
);

CREATE TABLE recommendations (
	recommendation_id INTEGER NOT NULL AUTO_INCREMENT, 
	run_id INTEGER NOT NULL, 
	snapshot_id INTEGER NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	approval_status VARCHAR(30) NOT NULL, 
	reason_code VARCHAR(100), 
	actions JSON NOT NULL, 
	input_payload JSON NOT NULL, 
	result_payload JSON NOT NULL, 
	decision_date DATE NOT NULL, 
	created_at DATETIME NOT NULL, 
	decided_at DATETIME, 
	decided_by_role VARCHAR(30), 
	PRIMARY KEY (recommendation_id), 
	CONSTRAINT uq_run_snapshot UNIQUE (run_id, snapshot_id), 
	FOREIGN KEY(run_id) REFERENCES recommendation_runs (run_id), 
	FOREIGN KEY(snapshot_id) REFERENCES inventory_snapshots (snapshot_id)
);

CREATE TABLE notifications (
	notification_id INTEGER NOT NULL AUTO_INCREMENT, 
	recommendation_id INTEGER NOT NULL, 
	store_id VARCHAR(40) NOT NULL, 
	message VARCHAR(500) NOT NULL, 
	created_at DATETIME NOT NULL, 
	read_at DATETIME, 
	PRIMARY KEY (notification_id), 
	UNIQUE (recommendation_id), 
	FOREIGN KEY(recommendation_id) REFERENCES recommendations (recommendation_id), 
	FOREIGN KEY(store_id) REFERENCES stores (store_id)
);
