#!/usr/bin/env python3
"""Grafana ダッシュボードを「コードから」生成する。

UI でポチポチ作る代わりにここで定義し、JSON を
stack/grafana/dashboards/ に出力する（dashboard as code）。

  python3 scripts/gen_dashboards.py
"""
from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "stack", "grafana", "dashboards")
SAT = "SAT-1"
BUCKET = "telemetry"   # INFLUXDB_BUCKET を変える場合はここも更新

DS_INFLUX = {"type": "influxdb", "uid": "influxdb"}
DS_PG = {"type": "postgres", "uid": "timescaledb"}
DS_PROM = {"type": "prometheus", "uid": "prometheus"}

_id = 0


def nid() -> int:
    global _id
    _id += 1
    return _id


# ── パネル・ビルダー ────────────────────────────────────
def _base(title, ds, gp, ptype):
    return {"id": nid(), "title": title, "type": ptype, "datasource": ds,
            "gridPos": gp, "targets": []}


def flux(query):
    return {"refId": "A", "datasource": DS_INFLUX, "query": query}


def sql(rawsql, fmt="table"):
    return {"refId": "A", "datasource": DS_PG, "rawSql": rawsql,
            "rawQuery": True, "format": fmt}


def prom(expr, legend=""):
    return {"refId": "A", "datasource": DS_PROM, "expr": expr,
            "legendFormat": legend}


def timeseries(title, ds, targets, gp, unit="short", legend=True):
    p = _base(title, ds, gp, "timeseries")
    p["targets"] = targets
    p["fieldConfig"] = {"defaults": {"unit": unit, "custom": {
        "drawStyle": "line", "lineWidth": 2, "fillOpacity": 8,
        "showPoints": "never"}}, "overrides": []}
    p["options"] = {"legend": {"showLegend": legend, "displayMode": "list",
                               "placement": "bottom"},
                    "tooltip": {"mode": "multi"}}
    return p


def gauge(title, ds, targets, gp, unit, thresholds):
    p = _base(title, ds, gp, "gauge")
    p["targets"] = targets
    p["fieldConfig"] = {"defaults": {"unit": unit, "thresholds": {
        "mode": "absolute", "steps": thresholds}}, "overrides": []}
    p["options"] = {"reduceOptions": {"calcs": ["lastNotNull"]},
                    "showThresholdLabels": False, "showThresholdMarkers": True}
    return p


def stat(title, ds, targets, gp, unit="short", color_mode="value",
         thresholds=None):
    p = _base(title, ds, gp, "stat")
    p["targets"] = targets
    th = thresholds or [{"color": "blue", "value": None}]
    p["fieldConfig"] = {"defaults": {"unit": unit, "thresholds": {
        "mode": "absolute", "steps": th}}, "overrides": []}
    p["options"] = {"reduceOptions": {"calcs": ["lastNotNull"]},
                    "colorMode": color_mode, "graphMode": "area",
                    "textMode": "auto"}
    return p


def table(title, ds, targets, gp):
    p = _base(title, ds, gp, "table")
    p["targets"] = targets
    p["fieldConfig"] = {"defaults": {"custom": {"filterable": True}},
                        "overrides": []}
    p["options"] = {"showHeader": True}
    return p


def barchart(title, ds, targets, gp, unit="short"):
    p = _base(title, ds, gp, "barchart")
    p["targets"] = targets
    p["fieldConfig"] = {"defaults": {"unit": unit}, "overrides": []}
    p["options"] = {"orientation": "horizontal",
                    "legend": {"showLegend": False}}
    return p


def piechart(title, ds, targets, gp):
    p = _base(title, ds, gp, "piechart")
    p["targets"] = targets
    p["options"] = {"legend": {"showLegend": True, "placement": "right"},
                    "pieType": "donut",
                    "reduceOptions": {"calcs": ["lastNotNull"]}}
    p["fieldConfig"] = {"defaults": {}, "overrides": []}
    return p


def state_timeline(title, ds, targets, gp):
    p = _base(title, ds, gp, "state-timeline")
    p["targets"] = targets
    p["fieldConfig"] = {"defaults": {"custom": {"fillOpacity": 80},
                        "thresholds": {"mode": "absolute", "steps": [
                            {"color": "dark-red", "value": None},
                            {"color": "green", "value": 1}]}},
                        "overrides": []}
    p["options"] = {"showValue": "never", "mergeValues": True,
                    "legend": {"showLegend": True}}
    return p


def geomap(title, targets, gp):
    p = _base(title, DS_PG, gp, "geomap")
    p["targets"] = targets
    p["options"] = {
        "view": {"id": "zero", "lat": 20, "lon": 0, "zoom": 1.5},
        "basemap": {"type": "default", "name": "Basemap"},
        "layers": [{
            "type": "markers", "name": "captures",
            "location": {"mode": "coords", "latitude": "latitude_deg",
                         "longitude": "longitude_deg"},
            "config": {"showLegend": True,
                       "style": {"color": {"fixed": "orange"},
                                 "size": {"fixed": 6}}},
        }],
        "controls": {"showZoom": True, "showAttribution": True},
    }
    p["fieldConfig"] = {"defaults": {}, "overrides": []}
    return p


def row(title, y):
    return {"id": nid(), "title": title, "type": "row", "collapsed": False,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}, "panels": []}


def gp(x, y, w, h):
    return {"x": x, "y": y, "w": w, "h": h}


def dashboard(uid, title, tags, panels, refresh="5s", from_="now-15m"):
    return {
        "uid": uid, "title": title, "tags": tags, "schemaVersion": 39,
        "version": 1, "editable": True, "refresh": refresh,
        "time": {"from": from_, "to": "now"},
        "timepicker": {}, "templating": {"list": []},
        "annotations": {"list": []}, "panels": panels,
    }


def soc_thresholds():
    return [{"color": "red", "value": None}, {"color": "yellow", "value": 30},
            {"color": "green", "value": 50}]


# ── 1) 衛星ヘルス (InfluxDB / Flux) ─────────────────────
def satellite_health():
    def f(meas, field):
        return (f'from(bucket: "{BUCKET}")\n'
                f'  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n'
                f'  |> filter(fn: (r) => r._measurement == "{meas}" '
                f'and r._field == "{field}")\n'
                f'  |> filter(fn: (r) => r.sat == "{SAT}")')

    panels = []
    panels.append(row("⚡ 電源 EPS", 0))
    panels.append(gauge("Battery SoC", DS_INFLUX, [flux(f("power", "battery_soc_pct"))],
                        gp(0, 1, 6, 8), "percent", soc_thresholds()))
    panels.append(timeseries("Bus Voltage", DS_INFLUX,
                  [flux(f("power", "bus_voltage_v"))], gp(6, 1, 9, 8), "volt"))
    panels.append(timeseries("Net Power", DS_INFLUX,
                  [flux(f("power", "net_power_w"))], gp(15, 1, 9, 8), "watt"))

    panels.append(row("🌡 熱 TCS", 9))
    thermal_q = (f'from(bucket: "{BUCKET}")\n'
                 f'  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n'
                 f'  |> filter(fn: (r) => r._measurement == "thermal" '
                 f'and r._field == "temp_c")\n'
                 f'  |> filter(fn: (r) => r.sat == "{SAT}")\n'
                 f'  |> keep(columns: ["_time", "_value", "zone"])')
    panels.append(timeseries("Zone Temperatures", DS_INFLUX, [flux(thermal_q)],
                  gp(0, 10, 16, 8), "celsius"))
    panels.append(timeseries("Battery Temp", DS_INFLUX,
                  [flux(f("power", "battery_temp_c"))], gp(16, 10, 8, 8),
                  "celsius"))

    panels.append(row("🛰 姿勢 ADCS", 18))
    panels.append(gauge("Pointing Error", DS_INFLUX,
                  [flux(f("attitude", "pointing_error_deg"))], gp(0, 19, 6, 8),
                  "degree", [{"color": "green", "value": None},
                             {"color": "yellow", "value": 2},
                             {"color": "red", "value": 5}]))
    rates_q = (f'from(bucket: "{BUCKET}")\n'
               f'  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n'
               f'  |> filter(fn: (r) => r._measurement == "attitude" and '
               f'(r._field == "roll_rate_dps" or r._field == "pitch_rate_dps" '
               f'or r._field == "yaw_rate_dps"))\n'
               f'  |> filter(fn: (r) => r.sat == "{SAT}")')
    panels.append(timeseries("Body Rates", DS_INFLUX, [flux(rates_q)],
                  gp(6, 19, 9, 8), "degree"))
    panels.append(timeseries("Reaction Wheel RPM", DS_INFLUX,
                  [flux(f("attitude", "reaction_wheel_rpm"))], gp(15, 19, 9, 8),
                  "rotrpm"))

    panels.append(row("📶 通信 COMM", 27))
    panels.append(timeseries("Downlink SNR", DS_INFLUX,
                  [flux(f("comms", "snr_db"))], gp(0, 28, 12, 8), "dB"))
    panels.append(timeseries("Downlink Rate", DS_INFLUX,
                  [flux(f("comms", "downlink_rate_mbps"))], gp(12, 28, 12, 8),
                  "Mbits"))
    return dashboard("sat-health", "🛰 Satellite Health",
                     ["space", "telemetry", "influxdb"], panels)


# ── 2) 地上局運用 (TimescaleDB / SQL) ───────────────────
def ground_station_ops():
    panels = []
    panels.append(stat("Contacts (24h)", DS_PG, [sql(
        "SELECT count(*) FROM passes WHERE aos > now() - interval '24 hours'")],
        gp(0, 0, 6, 5), "short", "value",
        [{"color": "blue", "value": None}]))
    panels.append(stat("Downlinked (24h)", DS_PG, [sql(
        "SELECT coalesce(sum(data_downlinked_mb),0) FROM passes "
        "WHERE aos > now() - interval '24 hours'")],
        gp(6, 0, 6, 5), "decmbytes", "value",
        [{"color": "green", "value": None}]))
    panels.append(stat("Active Pass", DS_PG, [sql(
        "SELECT count(*) FROM passes WHERE status = 'in_progress'")],
        gp(12, 0, 6, 5), "short", "background",
        [{"color": "dark-gray", "value": None}, {"color": "green", "value": 1}]))
    panels.append(stat("Ground Stations", DS_PG, [sql(
        "SELECT count(*) FROM ground_stations")],
        gp(18, 0, 6, 5), "short", "value",
        [{"color": "purple", "value": None}]))

    panels.append(timeseries("Pass Max Elevation", DS_PG, [sql(
        "SELECT p.aos AS time, p.max_elevation_deg AS elevation, g.code "
        "AS metric FROM passes p JOIN ground_stations g ON g.id = p.station_id "
        "WHERE p.max_elevation_deg IS NOT NULL ORDER BY p.aos", "time_series")],
        gp(0, 5, 16, 8), "degree"))
    panels.append(barchart("Downlink by Station (MB)", DS_PG, [sql(
        "SELECT g.name AS station, sum(p.data_downlinked_mb) AS mb FROM passes p "
        "JOIN ground_stations g ON g.id = p.station_id GROUP BY g.name "
        "ORDER BY mb DESC")], gp(16, 5, 8, 8), "decmbytes"))

    panels.append(table("Recent Passes", DS_PG, [sql(
        "SELECT g.name AS station, p.aos, p.los, "
        "round(p.max_elevation_deg::numeric,1) AS max_el_deg, "
        "p.duration_s, round(p.data_downlinked_mb::numeric,0) AS dl_mb, "
        "p.status FROM passes p JOIN ground_stations g ON g.id = p.station_id "
        "ORDER BY p.aos DESC LIMIT 20")], gp(0, 13, 16, 11)))
    panels.append(table("Station Master", DS_PG, [sql(
        "SELECT code, name, country, latitude_deg, longitude_deg, "
        "min_elevation_deg FROM ground_stations ORDER BY code")],
        gp(16, 13, 8, 11)))
    return dashboard("ground-ops", "📡 Ground Station Ops",
                     ["space", "ground", "timescaledb"], panels)


# ── 3) ミッション & 地球観測 (TimescaleDB + InfluxDB) ───
def mission_eo():
    panels = []
    panels.append(stat("Captures (24h)", DS_PG, [sql(
        "SELECT count(*) FROM eo_captures "
        "WHERE captured_at > now() - interval '24 hours'")],
        gp(0, 0, 5, 5), "short", "value",
        [{"color": "orange", "value": None}]))
    panels.append(stat("Imaged Data (24h)", DS_PG, [sql(
        "SELECT coalesce(sum(size_mb),0) FROM eo_captures "
        "WHERE captured_at > now() - interval '24 hours'")],
        gp(5, 0, 5, 5), "decmbytes", "value",
        [{"color": "green", "value": None}]))
    panels.append(stat("Onboard (not downlinked)", DS_PG, [sql(
        "SELECT count(*) FROM eo_captures WHERE status = 'onboard'")],
        gp(10, 0, 5, 5), "short", "value",
        [{"color": "yellow", "value": None}]))
    panels.append(piechart("Captures by Mode", DS_PG, [sql(
        "SELECT mode, count(*) AS n FROM eo_captures GROUP BY mode")],
        gp(15, 0, 9, 9)))

    panels.append(geomap("Capture Footprints", [sql(
        "SELECT captured_at AS time, latitude_deg, longitude_deg, "
        "target_name, size_mb FROM eo_captures "
        "ORDER BY captured_at DESC LIMIT 200")], gp(0, 5, 15, 9)))

    panels.append(timeseries("Onboard Data Buffer", DS_PG, [sql(
        "SELECT ts AS time, value FROM mission_kpi "
        "WHERE metric = 'data_buffer_pct' ORDER BY ts", "time_series")],
        gp(0, 14, 12, 8), "percent"))
    panels.append(table("Recent EO Captures", DS_PG, [sql(
        "SELECT captured_at, target_name, mode, frames, "
        "round(size_mb::numeric,0) AS size_mb, "
        "round(cloud_cover_pct::numeric,0) AS cloud_pct, status "
        "FROM eo_captures ORDER BY captured_at DESC LIMIT 20")],
        gp(12, 14, 12, 8)))
    return dashboard("mission-eo", "🌍 Mission & Earth Observation",
                     ["space", "mission", "timescaledb"], panels)


# ── 4) インフラ/リソース監視 (Prometheus) ────────────────
def infra_monitoring():
    panels = []
    panels.append(stat("Telemetry Link", DS_PROM,
                  [prom('up{job="satellite"}')], gp(0, 0, 4, 5), "short",
                  "background", [{"color": "red", "value": None},
                                 {"color": "green", "value": 1}]))
    panels.append(gauge("Battery SoC", DS_PROM,
                  [prom(f'sat_battery_soc_percent{{sat="{SAT}"}}')],
                  gp(4, 0, 5, 5), "percent", soc_thresholds()))
    panels.append(stat("Bus Voltage", DS_PROM,
                  [prom(f'sat_bus_voltage_volts{{sat="{SAT}"}}')],
                  gp(9, 0, 5, 5), "volt"))
    panels.append(stat("Eclipse", DS_PROM,
                  [prom(f'sat_in_eclipse{{sat="{SAT}"}}')], gp(14, 0, 5, 5),
                  "short", "background",
                  [{"color": "yellow", "value": None},
                   {"color": "dark-blue", "value": 1}]))
    panels.append(gauge("Pointing Error", DS_PROM,
                  [prom(f'sat_pointing_error_degrees{{sat="{SAT}"}}')],
                  gp(19, 0, 5, 5), "degree",
                  [{"color": "green", "value": None},
                   {"color": "yellow", "value": 2},
                   {"color": "red", "value": 5}]))

    panels.append(state_timeline("Ground Station Contact", DS_PROM,
                  [prom("sat_ground_contact", "{{station}}")],
                  gp(0, 5, 24, 6)))

    panels.append(timeseries("Subsystem Temperatures", DS_PROM,
                  [prom("sat_temperature_celsius", "{{zone}}")],
                  gp(0, 11, 12, 8), "celsius"))
    panels.append(timeseries("Downlink Rate", DS_PROM,
                  [prom("sat_downlink_rate_mbps", "downlink")],
                  gp(12, 11, 12, 8), "Mbits"))

    panels.append(timeseries("Onboard Data Buffer", DS_PROM,
                  [prom("sat_data_buffer_percent", "buffer")],
                  gp(0, 19, 12, 8), "percent"))
    panels.append(timeseries("Scrape Health", DS_PROM,
                  [prom('scrape_duration_seconds{job="satellite"}', "scrape")],
                  gp(12, 19, 12, 8), "s"))
    return dashboard("infra-mon", "🖥 Infrastructure & Resources",
                     ["space", "infra", "prometheus"], panels)


def main():
    os.makedirs(OUT, exist_ok=True)
    builders = {
        "satellite-health.json": satellite_health,
        "ground-station-ops.json": ground_station_ops,
        "mission-eo.json": mission_eo,
        "infra-monitoring.json": infra_monitoring,
    }
    for fname, builder in builders.items():
        global _id
        _id = 0
        dash = builder()
        with open(os.path.join(OUT, fname), "w") as f:
            json.dump(dash, f, indent=2, ensure_ascii=False)
        print(f"wrote {fname} ({len(dash['panels'])} panels)")


if __name__ == "__main__":
    main()
