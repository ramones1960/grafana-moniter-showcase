"""衛星サブシステムの簡易状態モデル（電源・熱・姿勢・通信）."""
from __future__ import annotations

import math
import random


class PowerModel:
    """EPS: 太陽発電・負荷・バッテリ SoC の積分."""

    def __init__(self, cfg: dict):
        self.cap_wh = cfg["battery_capacity_wh"]
        self.soc = cfg["initial_soc_pct"]
        self.gen_max = cfg["solar_generation_w"]
        self.base_load = cfg["base_load_w"]
        self.comms_load = cfg["comms_load_w"]
        self.payload_load = cfg["payload_load_w"]
        self.v_full = cfg["bus_voltage_full_v"]
        self.v_empty = cfg["bus_voltage_empty_v"]
        self.battery_temp = 18.0

    def step(self, dt_s: float, eclipse: bool, downlinking: bool, imaging: bool):
        gen = 0.0 if eclipse else self.gen_max * (0.9 + 0.1 * random.random())
        load = self.base_load
        if downlinking:
            load += self.comms_load
        if imaging:
            load += self.payload_load

        net_w = gen - load
        # SoC 変化 [%] = (W * h) / (Wh) * 100
        self.soc += (net_w * (dt_s / 3600.0)) / self.cap_wh * 100.0
        self.soc = max(0.0, min(100.0, self.soc))

        # 充放電でバッテリ温度がわずかに動く
        target_bt = 20.0 + (0.02 * net_w)
        self.battery_temp += (target_bt - self.battery_temp) * min(1.0, dt_s / 600.0)

    @property
    def bus_voltage(self) -> float:
        return self.v_empty + (self.v_full - self.v_empty) * (self.soc / 100.0)

    @property
    def solar_current(self) -> float:
        return 0.0  # placeholder; derived externally if needed


class ThermalModel:
    """TCS: ゾーンごとに日照/食の平衡温度へ一次遅れで緩和."""

    def __init__(self, cfg: dict):
        self.zones = cfg["zones"]
        self.temp = {z: p["sun"] for z, p in self.zones.items()}

    def step(self, dt_s: float, eclipse: bool):
        for z, p in self.zones.items():
            target = p["eclipse"] if eclipse else p["sun"]
            alpha = 1.0 - math.exp(-dt_s / p["tau"])
            self.temp[z] += (target - self.temp[z]) * alpha
            self.temp[z] += random.gauss(0, 0.15)


class AttitudeModel:
    """ADCS: ポインティング誤差・角速度・リアクションホイール回転数."""

    def __init__(self, cfg: dict):
        self.err_nom = cfg["pointing_error_nominal_deg"]
        self.rw_nom = cfg["reaction_wheel_nominal_rpm"]
        self.pointing_error = self.err_nom
        self.rw_rpm = self.rw_nom
        self.rates = [0.0, 0.0, 0.0]   # roll/pitch/yaw [deg/s]
        self._desat_t = 0.0

    def step(self, dt_s: float, sim_t: float):
        # 通常はわずかな誤差。たまにモメンタム蓄積で増加し、デサチュレーションで回復。
        self.rw_rpm += random.gauss(0, 3) + 0.4
        if self.rw_rpm > 5200 and self._desat_t <= 0:
            self._desat_t = 30.0  # デサチュレーション開始

        if self._desat_t > 0:
            self._desat_t -= dt_s
            self.pointing_error += (1.5 - self.pointing_error) * 0.15
            self.rw_rpm += (self.rw_nom - self.rw_rpm) * 0.2
        else:
            self.pointing_error += (self.err_nom - self.pointing_error) * 0.1
            self.pointing_error += abs(random.gauss(0, 0.08))

        self.rates = [random.gauss(0, 0.05) + self.pointing_error * 0.02
                      for _ in range(3)]


class CommsModel:
    """COMM: 地上局可視時のダウンリンク・SNR(仰角依存)・信号ロック."""

    def __init__(self, cfg: dict):
        self.rate_max = cfg["downlink_rate_max_mbps"]
        self.snr_max = cfg["snr_max_db"]
        self.snr_min = cfg["snr_min_db"]
        self.snr = 0.0
        self.downlink_rate = 0.0
        self.locked = False

    def step(self, elevation_deg: float, in_pass: bool, has_data: bool):
        if not in_pass or elevation_deg <= 0:
            self.snr = 0.0
            self.downlink_rate = 0.0
            self.locked = False
            return 0.0

        # 仰角 0->90deg を SNR レンジへマップ
        frac = min(1.0, elevation_deg / 60.0)
        self.snr = self.snr_min + (self.snr_max - self.snr_min) * frac
        self.snr += random.gauss(0, 0.4)
        self.locked = self.snr > 6.0 and has_data
        self.downlink_rate = self.rate_max * frac if self.locked else 0.0
        return self.downlink_rate
