"""衛星サブシステムの状態モデル（電源・熱・姿勢・通信）.

改善点:
- 電源 (EPS): β角依存太陽発電、バッテリヒータ (低温保護)、Li-ion非線形電圧曲線
- 熱  (TCS): 食移行時の熱スナップ外乱、ヒータ状態フィードバック
- 姿勢 (ADCS): 食移行外乱、デサチュレーション完了フラグ
- 通信 (COMM): 自由空間伝搬損失に基づくSNRモデル、信号獲得遅延
"""
from __future__ import annotations

import math
import random


class PowerModel:
    """EPS: β角依存太陽発電・負荷・バッテリ SoC 積分."""

    def __init__(self, cfg: dict):
        self.cap_wh = cfg["battery_capacity_wh"]
        self.soc = cfg["initial_soc_pct"]
        self.gen_max = cfg["solar_generation_w"]
        self.base_load = cfg["base_load_w"]
        self.comms_load = cfg["comms_load_w"]
        self.payload_load = cfg["payload_load_w"]
        self.v_full = cfg["bus_voltage_full_v"]
        self.v_empty = cfg["bus_voltage_empty_v"]
        self.heater_w = cfg.get("battery_heater_w", 8.0)
        self.battery_temp = 18.0
        self.heater_on = False
        self._solar_gen = 0.0    # 実発電量 [W]
        self._net_power = 0.0    # 正味電力 [W]

    def step(self, dt_s: float, eclipse: bool, downlinking: bool, imaging: bool,
             beta_deg: float = 0.0):
        if eclipse:
            self._solar_gen = 0.0
        else:
            # β角が大きいほど太陽パネル入射角が変化する。
            # 太陽追尾1軸パネルを想定: 実効発電 ≈ gen_max * (1 - 0.3*sin²β)
            # β=0°で最大、β≈66°で食が消える軌道(β角依存は小さい)。
            beta_rad = math.radians(abs(beta_deg))
            beta_factor = 1.0 - 0.30 * math.sin(beta_rad) ** 2
            noise = 0.97 + 0.03 * random.random()
            self._solar_gen = self.gen_max * beta_factor * noise

        load = self.base_load
        if downlinking:
            load += self.comms_load
        if imaging:
            load += self.payload_load

        # バッテリヒータ (低温保護 — バッテリ5℃以下で投入)
        self.heater_on = self.battery_temp < 5.0
        if self.heater_on:
            load += self.heater_w

        self._net_power = self._solar_gen - load
        self.soc += (self._net_power * (dt_s / 3600.0)) / self.cap_wh * 100.0
        self.soc = max(0.0, min(100.0, self.soc))

        # バッテリ温度: 環境温度 (日照/食) + 充放電発熱
        env_target = 8.0 if eclipse else 22.0
        charge_heat = abs(self._net_power) * 0.01  # 充放電効率ロスによる昇温
        target_bt = env_target + charge_heat
        self.battery_temp += (target_bt - self.battery_temp) * min(1.0, dt_s / 600.0)

    @property
    def bus_voltage(self) -> float:
        """Li-ion 電圧曲線の区分線形近似 (3段モデル)."""
        soc = max(0.0, min(100.0, self.soc)) / 100.0
        if soc >= 0.80:
            # 高SoC: 電圧変化が急 (27.6V → 29.4V)
            return 27.6 + (soc - 0.80) / 0.20 * (self.v_full - 27.6)
        elif soc >= 0.20:
            # 中SoC: 電圧変化が緩 (25.2V → 27.6V)
            return 25.2 + (soc - 0.20) / 0.60 * (27.6 - 25.2)
        else:
            # 低SoC: 電圧変化が急 (24.0V → 25.2V)
            return self.v_empty + soc / 0.20 * (25.2 - self.v_empty)

    @property
    def solar_generation_w(self) -> float:
        return self._solar_gen

    @property
    def net_power_w(self) -> float:
        return self._net_power


class ThermalModel:
    """TCS: ゾーンごとに日照/食の平衡温度へ一次遅れで緩和.

    食移行時に熱スナップ外乱 (構造ひずみ解放による急変) を加える。
    """

    def __init__(self, cfg: dict):
        self.zones = cfg["zones"]
        self.temp = {z: p["sun"] for z, p in self.zones.items()}
        self._was_eclipse = False

    def step(self, dt_s: float, eclipse: bool):
        # 食↔日照 移行フラグ
        transition = eclipse != self._was_eclipse
        self._was_eclipse = eclipse

        for z, p in self.zones.items():
            target = p["eclipse"] if eclipse else p["sun"]
            alpha = 1.0 - math.exp(-dt_s / p["tau"])
            self.temp[z] += (target - self.temp[z]) * alpha
            noise = random.gauss(0, 0.15)
            if transition:
                # 熱スナップ外乱 (ソーラーパネルで顕著)
                snap = 0.8 if z.startswith("panel") else 0.25
                noise += random.gauss(0, snap)
            self.temp[z] += noise


class AttitudeModel:
    """ADCS: ポインティング誤差・角速度・リアクションホイール回転数.

    - RW角運動量は環境外乱トルクで蓄積し、5200 rpm で自動デサチュレーション。
    - 食移行時に熱スナップ起因の外乱を加える。
    """

    def __init__(self, cfg: dict):
        self.err_nom = cfg["pointing_error_nominal_deg"]
        self.rw_nom = cfg["reaction_wheel_nominal_rpm"]
        self.pointing_error = self.err_nom
        self.rw_rpm = self.rw_nom
        self.rates = [0.0, 0.0, 0.0]   # roll/pitch/yaw [deg/s]
        self._desat_t = 0.0
        self._was_eclipse = False
        self.desatting = False

    def step(self, dt_s: float, sim_t: float, eclipse: bool = False):
        # 食移行外乱
        transition = eclipse != self._was_eclipse
        self._was_eclipse = eclipse

        # RW角運動量蓄積 (外乱トルク)
        self.rw_rpm += random.gauss(0, 3) + 0.4
        if self.rw_rpm > 5200 and self._desat_t <= 0:
            self._desat_t = 30.0  # デサチュレーション (30 sim秒)

        self.desatting = self._desat_t > 0
        if self.desatting:
            self._desat_t -= dt_s
            self.pointing_error += (1.5 - self.pointing_error) * 0.15
            self.rw_rpm += (self.rw_nom - self.rw_rpm) * 0.20
        else:
            self.pointing_error += (self.err_nom - self.pointing_error) * 0.10
            noise = abs(random.gauss(0, 0.08))
            if transition:
                # 食移行: 熱スナップによる姿勢外乱
                noise += abs(random.gauss(0, 0.35))
            self.pointing_error += noise

        self.rates = [
            random.gauss(0, 0.05) + self.pointing_error * 0.02
            for _ in range(3)
        ]


class CommsModel:
    """COMM: 地上局可視時のダウンリンク・SNR・信号ロック.

    - 自由空間伝搬損失モデル: SNR ∝ sin(el)
      (仰角が低いほどスラントレンジが長く損失大)
    - 大気シンチレーション雑音を加算
    - 信号獲得遅延: 2ステップ以上の連続可視でロック確立
    """

    def __init__(self, cfg: dict):
        self.rate_max = cfg["downlink_rate_max_mbps"]
        self.snr_max = cfg["snr_max_db"]
        self.snr_min = cfg["snr_min_db"]
        self.snr = 0.0
        self.downlink_rate = 0.0
        self.locked = False
        self._visible_steps = 0  # 連続可視ステップ数 (信号獲得遅延に使用)

    def step(self, elevation_deg: float, in_pass: bool, has_data: bool):
        if not in_pass or elevation_deg <= 0:
            self.snr = 0.0
            self.downlink_rate = 0.0
            self.locked = False
            self._visible_steps = 0
            return 0.0

        self._visible_steps += 1

        # 自由空間伝搬損失ベースSNR: L_FSPL ∝ 1/sin(el)^2
        # → SNR を仰角 sin の平方根でスケール (実効SNRレンジ内に収める)
        el_rad = math.radians(max(1.0, elevation_deg))
        el_factor = math.sqrt(math.sin(el_rad))  # 0~1
        # 大気シンチレーション雑音 (低仰角で大きい)
        scintillation = random.gauss(0, max(0.3, 1.2 * (1.0 - el_factor)))
        self.snr = (
            self.snr_min
            + (self.snr_max - self.snr_min) * el_factor
            + scintillation
        )

        # 信号獲得: SNR > 6dB かつ 2 ステップ以上の連続可視でロック
        self.locked = (
            self._visible_steps >= 2
            and self.snr > 6.0
            and has_data
        )
        self.downlink_rate = self.rate_max * el_factor if self.locked else 0.0
        return self.downlink_rate
