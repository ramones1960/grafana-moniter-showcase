"""出力先 (sinks): InfluxDB / TimescaleDB / Prometheus へのアダプタ."""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import psycopg2
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from prometheus_client import Gauge, start_http_server


def _retry(fn, desc, attempts=30, delay=2.0):
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"[sinks] {desc} 待機中 ({i + 1}/{attempts}): {e}", flush=True)
            time.sleep(delay)
    raise RuntimeError(f"{desc} に接続できませんでした: {last}")


# ── InfluxDB (高頻度テレメトリ) ─────────────────────────
class InfluxSink:
    def __init__(self):
        self.bucket = os.environ["INFLUXDB_BUCKET"]
        self.org = os.environ["INFLUXDB_ORG"]
        self.sat = None
        url = os.environ["INFLUXDB_URL"]
        token = os.environ["INFLUXDB_TOKEN"]

        def connect():
            c = InfluxDBClient(url=url, token=token, org=self.org)
            if not c.ping():
                raise RuntimeError("ping failed")
            return c

        self.client = _retry(connect, "InfluxDB")
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)

    def write(self, sat: str, ts: datetime, tele: dict):
        pts = []
        p = tele["power"]
        pts.append(Point("power").tag("sat", sat)
                   .field("bus_voltage_v", p["bus_voltage_v"])
                   .field("battery_soc_pct", p["battery_soc_pct"])
                   .field("battery_temp_c", p["battery_temp_c"])
                   .field("solar_generation_w", p["solar_generation_w"])
                   .field("net_power_w", p["net_power_w"])
                   .field("heater_on", p["heater_on"])
                   .time(ts))

        for zone, t in tele["thermal"].items():
            pts.append(Point("thermal").tag("sat", sat).tag("zone", zone)
                       .field("temp_c", t).time(ts))

        a = tele["attitude"]
        pts.append(Point("attitude").tag("sat", sat)
                   .field("pointing_error_deg", a["pointing_error_deg"])
                   .field("roll_rate_dps", a["roll_rate_dps"])
                   .field("pitch_rate_dps", a["pitch_rate_dps"])
                   .field("yaw_rate_dps", a["yaw_rate_dps"])
                   .field("reaction_wheel_rpm", a["reaction_wheel_rpm"])
                   .field("desaturating", a["desaturating"])
                   .time(ts))

        c = tele["comms"]
        pts.append(Point("comms").tag("sat", sat).tag("station", c["station"] or "none")
                   .field("snr_db", c["snr_db"])
                   .field("downlink_rate_mbps", c["downlink_rate_mbps"])
                   .field("signal_lock", 1 if c["signal_lock"] else 0).time(ts))

        o = tele["orbit"]
        pts.append(Point("orbit").tag("sat", sat)
                   .field("lat", o["lat"]).field("lon", o["lon"])
                   .field("alt_km", o["alt_km"])
                   .field("eclipse", 1 if o["eclipse"] else 0)
                   .field("beta_deg", o["beta_deg"]).time(ts))

        self.write_api.write(bucket=self.bucket, org=self.org, record=pts)


# ── TimescaleDB (台帳・イベント) ────────────────────────
class TimescaleSink:
    def __init__(self):
        def connect():
            c = psycopg2.connect(
                host=os.environ["TIMESCALE_HOST"],
                dbname=os.environ["TIMESCALE_DB"],
                user=os.environ["TIMESCALE_USER"],
                password=os.environ["TIMESCALE_PASSWORD"],
            )
            c.autocommit = True
            return c

        self.conn = _retry(connect, "TimescaleDB")
        self.stations = {}        # code -> id
        self.station_meta = {}    # code -> dict(lat, lon, min_el)
        self._load_stations()

    def _load_stations(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT code, id, latitude_deg, longitude_deg, "
                        "min_elevation_deg FROM ground_stations")
            for code, sid, lat, lon, min_el in cur.fetchall():
                self.stations[code] = sid
                self.station_meta[code] = {"lat": lat, "lon": lon, "min_el": min_el}

    def open_pass(self, sat: str, station_code: str, aos: datetime) -> int:
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO passes (sat, station_id, aos, status) "
                "VALUES (%s, %s, %s, 'in_progress') RETURNING id",
                (sat, self.stations[station_code], aos),
            )
            return cur.fetchone()[0]

    def close_pass(self, pass_id: int, aos: datetime, los: datetime,
                   max_el: float, downlinked_mb: float,
                   rise_az: float = 0.0, set_az: float = 0.0):
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE passes SET los=%s, max_elevation_deg=%s, "
                "duration_s=%s, data_downlinked_mb=%s, "
                "rise_az_deg=%s, set_az_deg=%s, status='completed' "
                "WHERE id=%s AND aos=%s",
                (los, max_el, int((los - aos).total_seconds()),
                 downlinked_mb, rise_az, set_az, pass_id, aos),
            )

    def add_capture(self, sat: str, ts: datetime, target: str, lat: float,
                    lon: float, mode: str, frames: int, size_mb: float,
                    cloud: float):
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO eo_captures (sat, captured_at, target_name, "
                "latitude_deg, longitude_deg, mode, frames, size_mb, "
                "cloud_cover_pct, status) VALUES "
                "(%s,%s,%s,%s,%s,%s,%s,%s,%s,'onboard')",
                (sat, ts, target, lat, lon, mode, frames, size_mb, cloud),
            )

    def mark_downlinked(self, sat: str):
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE eo_captures SET status='downlinked' "
                "WHERE sat=%s AND status='onboard'", (sat,))

    def add_kpi(self, sat: str, ts: datetime, metric: str, value: float):
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO mission_kpi (ts, sat, metric, value) "
                "VALUES (%s,%s,%s,%s)", (ts, sat, metric, value))

    def add_anomaly(self, sat: str, ts: datetime, subsystem: str,
                    severity: str, message: str):
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO anomalies (ts, sat, subsystem, severity, message) "
                "VALUES (%s,%s,%s,%s,%s)",
                (ts, sat, subsystem, severity, message))

    def insert_predicted_passes(self, sat: str, predictions,
                                time_scale: float, wall_start: float):
        """将来パス予測を DB に挿入する.

        既存の未来予測を削除してから新規予測を挿入する。
        PredictedPass の t_aos / t_los はシミュレーション秒 (wall_start からの
        sim-s) なので、実UTC = wall_start + sim_t / time_scale で変換する。

        Args:
            predictions: list of PredictedPass (orbit.py)
            time_scale: シミュレーション加速倍率
            wall_start: シミュレーション開始 wall clock (time.time())
        """
        with self.conn.cursor() as cur:
            # 未来の予測エントリを削除
            cur.execute(
                "DELETE FROM predicted_passes WHERE sat=%s AND t_aos > now()",
                (sat,),
            )
            inserted = 0
            for p in predictions:
                real_aos = wall_start + p.t_aos / time_scale
                real_los = wall_start + p.t_los / time_scale
                dt_aos = datetime.fromtimestamp(real_aos, tz=timezone.utc)
                dt_los = datetime.fromtimestamp(real_los, tz=timezone.utc)
                sid = self.stations.get(p.station)
                if sid is None:
                    continue
                real_duration = max(0, int((real_los - real_aos)))
                cur.execute(
                    "INSERT INTO predicted_passes "
                    "(sat, station_id, t_aos, t_los, max_elevation_deg, "
                    "rise_az_deg, max_az_deg, set_az_deg, duration_s) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (sat, sid, dt_aos, dt_los, p.max_el,
                     p.rise_az, p.max_az, p.set_az, real_duration),
                )
                inserted += 1
        print(f"[sinks] {inserted} パス予測を挿入 ({sat})", flush=True)


# ── Prometheus (業務メトリクス) ─────────────────────────
class PromSink:
    def __init__(self, port: int):
        self.soc = Gauge("sat_battery_soc_percent", "Battery state of charge", ["sat"])
        self.volt = Gauge("sat_bus_voltage_volts", "Bus voltage", ["sat"])
        self.solar = Gauge("sat_solar_generation_watts", "Solar panel generation", ["sat"])
        self.net_pwr = Gauge("sat_net_power_watts", "Net power (gen - load)", ["sat"])
        self.heater = Gauge("sat_battery_heater_active", "Battery heater active", ["sat"])
        self.temp = Gauge("sat_temperature_celsius", "Subsystem temperature",
                          ["sat", "zone"])
        self.point_err = Gauge("sat_pointing_error_degrees", "ADCS pointing error",
                               ["sat"])
        self.rw_rpm = Gauge("sat_reaction_wheel_rpm", "Reaction wheel speed", ["sat"])
        self.downlink = Gauge("sat_downlink_rate_mbps", "Downlink rate", ["sat"])
        self.eclipse = Gauge("sat_in_eclipse", "1 if in eclipse", ["sat"])
        self.beta = Gauge("sat_beta_angle_degrees", "Solar beta angle", ["sat"])
        self.contact = Gauge("sat_ground_contact", "1 if station visible",
                             ["sat", "station"])
        self.buffer = Gauge("sat_data_buffer_percent", "Onboard data buffer fill",
                            ["sat"])
        self.altitude = Gauge("sat_altitude_km", "Orbital altitude", ["sat"])
        start_http_server(port)

    def update(self, sat: str, tele: dict, buffer_pct: float, contacts: dict):
        p, o, a = tele["power"], tele["orbit"], tele["attitude"]
        self.soc.labels(sat).set(p["battery_soc_pct"])
        self.volt.labels(sat).set(p["bus_voltage_v"])
        self.solar.labels(sat).set(p["solar_generation_w"])
        self.net_pwr.labels(sat).set(p["net_power_w"])
        self.heater.labels(sat).set(p["heater_on"])
        self.point_err.labels(sat).set(a["pointing_error_deg"])
        self.rw_rpm.labels(sat).set(a["reaction_wheel_rpm"])
        self.downlink.labels(sat).set(tele["comms"]["downlink_rate_mbps"])
        self.eclipse.labels(sat).set(1 if o["eclipse"] else 0)
        self.beta.labels(sat).set(o["beta_deg"])
        self.buffer.labels(sat).set(buffer_pct)
        self.altitude.labels(sat).set(o["alt_km"])
        for zone, t in tele["thermal"].items():
            self.temp.labels(sat, zone).set(t)
        for code, visible in contacts.items():
            self.contact.labels(sat, code).set(1 if visible else 0)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
