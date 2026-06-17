-- 地上局 / ミッション運用台帳スキーマ (TimescaleDB)
-- 模擬テレメトリ生成器が passes / eo_captures / mission_kpi / anomalies に書き込む。

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ── 地上局マスタ ─────────────────────────────────────
CREATE TABLE ground_stations (
    id               SERIAL PRIMARY KEY,
    code             TEXT UNIQUE NOT NULL,
    name             TEXT NOT NULL,
    country          TEXT,
    latitude_deg     DOUBLE PRECISION NOT NULL,
    longitude_deg    DOUBLE PRECISION NOT NULL,
    min_elevation_deg DOUBLE PRECISION NOT NULL DEFAULT 5.0
);

INSERT INTO ground_stations (code, name, country, latitude_deg, longitude_deg, min_elevation_deg) VALUES
    ('SVL', 'Svalbard',  'Norway', 78.23,  15.39, 5.0),
    ('TKO', 'Katsuura',  'Japan',  35.20, 140.31, 5.0),
    ('FBK', 'Fairbanks', 'USA',    64.84, -147.72, 5.0),
    ('SCL', 'Santiago',  'Chile', -33.45, -70.66, 5.0);

-- ── 可視パス / コンタクト実績 ────────────────────────
CREATE TABLE passes (
    id               BIGSERIAL,
    sat              TEXT NOT NULL,
    station_id       INTEGER NOT NULL REFERENCES ground_stations(id),
    aos              TIMESTAMPTZ NOT NULL,          -- Acquisition of Signal
    los              TIMESTAMPTZ,                    -- Loss of Signal (NULL=進行中)
    max_elevation_deg DOUBLE PRECISION,
    duration_s       INTEGER,
    data_downlinked_mb DOUBLE PRECISION DEFAULT 0,
    status           TEXT NOT NULL DEFAULT 'in_progress', -- in_progress|completed
    PRIMARY KEY (id, aos)
);
SELECT create_hypertable('passes', 'aos', if_not_exists => TRUE);
CREATE INDEX ON passes (station_id, aos DESC);

-- ── 地球観測キャプチャ ───────────────────────────────
CREATE TABLE eo_captures (
    id               BIGSERIAL,
    sat              TEXT NOT NULL,
    captured_at      TIMESTAMPTZ NOT NULL,
    target_name      TEXT NOT NULL,
    latitude_deg     DOUBLE PRECISION,
    longitude_deg    DOUBLE PRECISION,
    mode             TEXT,                            -- pan|multispectral|sar
    frames           INTEGER,
    size_mb          DOUBLE PRECISION,
    cloud_cover_pct  DOUBLE PRECISION,
    status           TEXT DEFAULT 'onboard',          -- onboard|downlinked
    PRIMARY KEY (id, captured_at)
);
SELECT create_hypertable('eo_captures', 'captured_at', if_not_exists => TRUE);

-- ── ミッション KPI（時系列メトリクスのスナップショット）──
CREATE TABLE mission_kpi (
    ts               TIMESTAMPTZ NOT NULL,
    sat              TEXT NOT NULL,
    metric           TEXT NOT NULL,
    value            DOUBLE PRECISION NOT NULL
);
SELECT create_hypertable('mission_kpi', 'ts', if_not_exists => TRUE);
CREATE INDEX ON mission_kpi (metric, ts DESC);

-- ── 異常記録 (FDIR イベントログ) ─────────────────────
CREATE TABLE anomalies (
    id               BIGSERIAL,
    ts               TIMESTAMPTZ NOT NULL,
    sat              TEXT NOT NULL,
    subsystem        TEXT NOT NULL,
    severity         TEXT NOT NULL,                   -- info|warning|critical
    message          TEXT NOT NULL,
    PRIMARY KEY (id, ts)
);
SELECT create_hypertable('anomalies', 'ts', if_not_exists => TRUE);
