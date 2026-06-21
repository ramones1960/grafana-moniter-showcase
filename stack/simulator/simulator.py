"""模擬テレメトリ生成器 — エントリポイント.

物理計算は加速したシミュレーション時刻 (sim_elapsed) で行い、
DB 書き込みのタイムスタンプは実時刻 (utcnow) を使う。
これにより 1 周回 (~95分) が実時間 ~95秒 で進み、Grafana の
「直近N分」表示と自然に噛み合う。

改善点:
- β角を PowerModel に渡し、太陽発電量を現実的に変動させる
- 食移行フラグを AttitudeModel に渡し、熱スナップ外乱を再現
- 実際の太陽発電量・ヒータ状態をテレメトリに追加
- 将来 5 周回分のコンタクトウィンドウを定期的に予測・DB 格納
- 地上局仰角に加えて方位角も記録する
"""
from __future__ import annotations

import math
import os
import random
import time

import yaml

from orbit import Orbit
from sinks import InfluxSink, PromSink, TimescaleSink, utcnow
from subsystems import AttitudeModel, CommsModel, PowerModel, ThermalModel

HERE = os.path.dirname(__file__)

# パス予測を再計算するシミュレーション時間間隔 [周回数]
PRED_INTERVAL_ORBITS = 4


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class Simulator:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.sat = cfg["satellite"]["name"]
        self.orbit = Orbit(cfg["satellite"]["altitude_km"],
                           cfg["satellite"]["inclination_deg"],
                           cfg["satellite"]["raan_deg"])
        self.power = PowerModel(cfg["power"])
        self.thermal = ThermalModel(cfg["thermal"])
        self.attitude = AttitudeModel(cfg["attitude"])
        self.comms = CommsModel(cfg["comms"])

        self.buffer_cap_mb = cfg["mission"]["data_buffer_capacity_gb"] * 1024
        self.buffer_mb = self.buffer_cap_mb * 0.15
        self.capture_size = cfg["mission"]["capture_size_mb"]
        self.targets = cfg["mission"]["targets"]

        self.time_scale = float(os.environ.get("SIM_TIME_SCALE", "60"))
        self.interval = float(os.environ.get("SIM_INTERVAL_SEC", "1.0"))

        self.influx = InfluxSink()
        self.tsdb = TimescaleSink()
        self.prom = PromSink(int(os.environ.get("PROM_PORT", "8000")))

        # パス状態
        self.active_pass = None   # dict(id, code, aos, max_el, downlinked_mb)
        # アラート状態（重複記録防止）
        self._alerted = set()
        self._last_capture_t = -1e9
        self._kpi_accum = {"downlinked_mb": 0.0, "captures": 0}
        self._last_kpi_real = time.time()

        # パス予測スケジュール
        self._pred_interval_sim = PRED_INTERVAL_ORBITS * self.orbit.period_s
        self._last_pred_sim_t = -self._pred_interval_sim  # 起動直後に即実行
        self._sim_start: float = 0.0  # wall clock 起動時刻 (run() で設定)

    # ── 地上局可視判定 (仰角 + 方位角) ─────────────────
    def visible_stations(self, sat_ecef) -> dict:
        out = {}
        for code, meta in self.tsdb.station_meta.items():
            el = self.orbit.elevation_deg(sat_ecef, meta["lat"], meta["lon"])
            az = self.orbit.azimuth_deg(sat_ecef, meta["lat"], meta["lon"])
            out[code] = {"el": el, "az": az, "visible": el >= meta["min_el"]}
        return out

    # ── 地球観測撮像トリガ ───────────────────────────
    def maybe_capture(self, lat, lon, eclipse, sim_t, now):
        if eclipse or self.buffer_mb > self.buffer_cap_mb * 0.97:
            return
        if sim_t - self._last_capture_t < 240:   # 最短撮像間隔(sim秒)
            return
        for tgt in self.targets:
            if haversine_km(lat, lon, tgt["lat"], tgt["lon"]) < 700:
                mode = random.choice(["pan", "multispectral", "sar"])
                frames = random.randint(3, 12)
                cloud = round(random.uniform(0, 60), 1)
                self.tsdb.add_capture(self.sat, now, tgt["name"], tgt["lat"],
                                      tgt["lon"], mode, frames,
                                      self.capture_size, cloud)
                self.buffer_mb = min(self.buffer_cap_mb,
                                     self.buffer_mb + self.capture_size)
                self._last_capture_t = sim_t
                self._kpi_accum["captures"] += 1
                print(f"[sim] 撮像: {tgt['name']} ({mode}, {frames}frames)",
                      flush=True)
                return

    # ── パス管理 ─────────────────────────────────────
    def manage_pass(self, vis: dict, now, downlinked_now_mb: float):
        # 最も仰角の高い可視局を選ぶ
        best = max((c for c in vis.items() if c[1]["visible"]),
                   key=lambda kv: kv[1]["el"], default=None)

        if best and self.active_pass is None:
            code = best[0]
            pid = self.tsdb.open_pass(self.sat, code, now)
            self.active_pass = {"id": pid, "code": code, "aos": now,
                                "max_el": best[1]["el"],
                                "rise_az": best[1]["az"],
                                "downlinked_mb": 0.0}
            print(f"[sim] AOS {code} (el={best[1]['el']:.1f}° az={best[1]['az']:.0f}°)",
                  flush=True)
        elif self.active_pass is not None:
            ap = self.active_pass
            ap["downlinked_mb"] += downlinked_now_mb
            still = vis[ap["code"]]["visible"]
            if still:
                ap["max_el"] = max(ap["max_el"], vis[ap["code"]]["el"])
            else:
                set_az = vis[ap["code"]]["az"]
                self.tsdb.close_pass(ap["id"], ap["aos"], now, ap["max_el"],
                                     ap["downlinked_mb"],
                                     ap.get("rise_az", 0.0), set_az)
                self.tsdb.mark_downlinked(self.sat)
                self._kpi_accum["downlinked_mb"] += ap["downlinked_mb"]
                print(f"[sim] LOS {ap['code']} max_el={ap['max_el']:.1f}° "
                      f"dl={ap['downlinked_mb']:.0f}MB", flush=True)
                self.active_pass = None

    # ── 将来パス予測 & DB 格納 ────────────────────────
    def refresh_pass_predictions(self, sim_t: float):
        print("[sim] パス予測計算中...", flush=True)
        predictions = self.orbit.predict_passes(
            self.tsdb.station_meta,
            t_start=sim_t,
            n_orbits=5,
            step_s=20.0,
        )
        self.tsdb.insert_predicted_passes(
            self.sat, predictions,
            time_scale=self.time_scale,
            wall_start=self._sim_start,
        )
        print(f"[sim] {len(predictions)} パス予測を格納", flush=True)

    # ── アラート → anomalies テーブル ────────────────
    def check_anomalies(self, tele, now, buffer_pct):
        checks = [
            ("eps", "battery_critical", tele["power"]["battery_soc_pct"] < 20,
             "critical", "バッテリSoCが20%未満"),
            ("eps", "battery_low", tele["power"]["battery_soc_pct"] < 30,
             "warning", "バッテリSoCが30%未満"),
            ("adcs", "attitude_loss", tele["attitude"]["pointing_error_deg"] > 5,
             "critical", "ポインティング誤差が5度超過"),
            ("obc", "buffer_full", buffer_pct > 90,
             "warning", "オンボードバッファ90%超過"),
        ]
        for sub, key, cond, sev, msg in checks:
            if cond and key not in self._alerted:
                self.tsdb.add_anomaly(self.sat, now, sub, sev, msg)
                self._alerted.add(key)
                print(f"[sim] ANOMALY[{sev}] {msg}", flush=True)
            elif not cond:
                self._alerted.discard(key)

    # ── メインループ ─────────────────────────────────
    def run(self):
        print(f"[sim] start: period={self.orbit.period_s/60:.1f}min "
              f"time_scale={self.time_scale}", flush=True)
        start = time.time()
        self._sim_start = start  # wall clock 起動時刻を保存

        while True:
            sim_t = (time.time() - start) * self.time_scale
            dt = self.interval * self.time_scale
            now = utcnow()

            # ── 軌道 ──
            p_eci = self.orbit.position_eci(sim_t)
            p_ecef = self.orbit.eci_to_ecef(p_eci, sim_t)
            lat, lon, alt = self.orbit.ecef_to_geodetic(p_ecef)
            eclipse = self.orbit.in_eclipse(sim_t)
            beta = self.orbit.beta_angle_deg(sim_t)

            vis = self.visible_stations(p_ecef)
            in_pass = self.active_pass is not None or any(
                v["visible"] for v in vis.values())
            cur_code = self.active_pass["code"] if self.active_pass else None
            cur_el = vis[cur_code]["el"] if cur_code else max(
                (v["el"] for v in vis.values()), default=0.0)

            has_data = self.buffer_mb > 1.0
            imaging = (not eclipse) and (sim_t - self._last_capture_t < dt * 1.5)

            # ── サブシステム更新 ──
            downlinking = in_pass and has_data
            self.power.step(dt, eclipse, downlinking, imaging, beta_deg=beta)
            self.thermal.step(dt, eclipse)
            self.attitude.step(dt, sim_t, eclipse=eclipse)
            rate = self.comms.step(cur_el, in_pass, has_data)

            # ダウンリンク量 [MB] = rate[Mbps] * dt[s] / 8
            dl_mb = rate * dt / 8.0
            if dl_mb > 0:
                dl_mb = min(dl_mb, self.buffer_mb)
                self.buffer_mb -= dl_mb

            self.maybe_capture(lat, lon, eclipse, sim_t, now)

            buffer_pct = 100.0 * self.buffer_mb / self.buffer_cap_mb

            tele = {
                "power": {
                    "bus_voltage_v": round(self.power.bus_voltage, 3),
                    "battery_soc_pct": round(self.power.soc, 2),
                    "battery_temp_c": round(self.power.battery_temp, 2),
                    "solar_generation_w": round(self.power.solar_generation_w, 1),
                    "net_power_w": round(self.power.net_power_w, 1),
                    "heater_on": 1 if self.power.heater_on else 0,
                },
                "thermal": {z: round(t, 2) for z, t in self.thermal.temp.items()},
                "attitude": {
                    "pointing_error_deg": round(self.attitude.pointing_error, 3),
                    "roll_rate_dps": round(self.attitude.rates[0], 4),
                    "pitch_rate_dps": round(self.attitude.rates[1], 4),
                    "yaw_rate_dps": round(self.attitude.rates[2], 4),
                    "reaction_wheel_rpm": round(self.attitude.rw_rpm, 1),
                    "desaturating": 1 if self.attitude.desatting else 0,
                },
                "comms": {
                    "station": cur_code,
                    "snr_db": round(self.comms.snr, 2),
                    "downlink_rate_mbps": round(self.comms.downlink_rate, 2),
                    "signal_lock": self.comms.locked,
                },
                "orbit": {
                    "lat": round(lat, 4), "lon": round(lon, 4),
                    "alt_km": round(alt, 2), "eclipse": eclipse,
                    "beta_deg": round(beta, 2),
                },
            }

            # ── 出力 ──
            self.influx.write(self.sat, now, tele)
            self.manage_pass(vis, now, dl_mb)
            self.check_anomalies(tele, now, buffer_pct)
            self.prom.update(self.sat, tele, buffer_pct,
                             {c: v["visible"] for c, v in vis.items()})

            # ── ミッション KPI スナップショット (実時間で約30秒毎) ──
            if time.time() - self._last_kpi_real > 30:
                self.tsdb.add_kpi(self.sat, now, "data_buffer_pct", buffer_pct)
                self.tsdb.add_kpi(self.sat, now, "battery_soc_pct",
                                  self.power.soc)
                self.tsdb.add_kpi(self.sat, now, "solar_generation_w",
                                  self.power.solar_generation_w)
                self.tsdb.add_kpi(self.sat, now, "downlinked_mb_30s",
                                  self._kpi_accum["downlinked_mb"])
                self.tsdb.add_kpi(self.sat, now, "captures_30s",
                                  self._kpi_accum["captures"])
                self._kpi_accum = {"downlinked_mb": 0.0, "captures": 0}
                self._last_kpi_real = time.time()

            # ── パス予測更新 (N周回毎) ──
            if sim_t - self._last_pred_sim_t >= self._pred_interval_sim:
                self.refresh_pass_predictions(sim_t)
                self._last_pred_sim_t = sim_t

            time.sleep(self.interval)


def main():
    with open(os.path.join(HERE, "config.yaml")) as f:
        cfg = yaml.safe_load(f)
    Simulator(cfg).run()


if __name__ == "__main__":
    main()
