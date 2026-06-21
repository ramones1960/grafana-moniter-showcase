"""軌道伝播モデル.

円軌道 + J2摂動(扁平率による永年変化)を考慮する。
- RAAN永年変化: SSO では ~1°/day の東向き歳差
- 近点引数永年変化: 約 -3.4°/day (SSO, i=97.6°)
- 太陽方向: 黄道傾斜23.44° を考慮した簡易モデル
- 地上局仰角・方位角: NEU局所座標系
- パス予測: 将来N周回分のコンタクトウィンドウを解析的に計算
"""
from __future__ import annotations

import math
from dataclasses import dataclass

MU = 398600.4418            # 地球重力定数 [km^3/s^2]
R_EARTH = 6371.0            # 地球平均半径 [km]
OMEGA_EARTH = 7.2921159e-5  # 地球自転角速度 [rad/s]
OBLIQUITY = math.radians(23.439)  # 黄道傾斜角
YEAR_SEC = 365.25 * 86400.0
J2 = 1.08263e-3             # 地球帯状調和係数 (扁平摂動)

Vec3 = tuple[float, float, float]


def _rot_x(v: Vec3, a: float) -> Vec3:
    c, s = math.cos(a), math.sin(a)
    x, y, z = v
    return (x, c * y - s * z, s * y + c * z)


def _rot_z(v: Vec3, a: float) -> Vec3:
    c, s = math.cos(a), math.sin(a)
    x, y, z = v
    return (c * x - s * y, s * x + c * y, z)


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(a: Vec3) -> float:
    return math.sqrt(_dot(a, a))


def _unit(a: Vec3) -> Vec3:
    n = _norm(a)
    return (a[0] / n, a[1] / n, a[2] / n) if n else (0.0, 0.0, 0.0)


@dataclass
class StationView:
    code: str
    elevation_deg: float
    azimuth_deg: float
    visible: bool


@dataclass
class PredictedPass:
    """予測コンタクトウィンドウ."""
    station: str
    t_aos: float        # シミュレーション秒 (絶対)
    t_los: float
    max_el: float       # 最大仰角 [deg]
    rise_az: float      # AOS 時の方位角 [deg]
    max_az: float       # 最大仰角時の方位角 [deg]
    set_az: float       # LOS 時の方位角 [deg]
    duration_s: float   # パス継続時間 [sim秒]


class Orbit:
    def __init__(self, altitude_km: float, inclination_deg: float, raan_deg: float):
        self.a = R_EARTH + altitude_km
        self.incl = math.radians(inclination_deg)
        self.raan0 = math.radians(raan_deg)
        self.n = math.sqrt(MU / self.a ** 3)   # 平均運動 [rad/s]
        self.period_s = 2 * math.pi / self.n

        # J2摂動による永年変化率 (円軌道 e=0 近似)
        ratio = (R_EARTH / self.a) ** 2
        self._raan_dot = (
            -1.5 * self.n * ratio * J2 * math.cos(self.incl)
        )  # [rad/sim-s] RAAN永年変化 (SSO ~+1°/day)
        self._aop_dot = (
            0.75 * self.n * ratio * J2 * (5.0 * math.cos(self.incl) ** 2 - 1.0)
        )  # [rad/sim-s] 近点引数永年変化

    def _raan_at(self, t: float) -> float:
        return self.raan0 + self._raan_dot * t

    # ── 衛星位置 (ECI) ────────────────────────────────
    def position_eci(self, t: float) -> Vec3:
        # 真近点角 = 平均運動 + 近点引数永年変化
        nu = (self.n + self._aop_dot) * t
        raan = self._raan_at(t)
        r_pf: Vec3 = (self.a * math.cos(nu), self.a * math.sin(nu), 0.0)
        return _rot_z(_rot_x(r_pf, self.incl), raan)

    def normal_eci(self, t: float) -> Vec3:
        raan = self._raan_at(t)
        return _unit(_rot_z(_rot_x((0.0, 0.0, 1.0), self.incl), raan))

    # ── 太陽方向 (ECI) ────────────────────────────────
    @staticmethod
    def sun_eci(t: float) -> Vec3:
        lam = 2 * math.pi * (t % YEAR_SEC) / YEAR_SEC      # 黄経
        return _unit((
            math.cos(lam),
            math.sin(lam) * math.cos(OBLIQUITY),
            math.sin(lam) * math.sin(OBLIQUITY),
        ))

    # ── ECI -> ECEF -> 測地座標 ───────────────────────
    @staticmethod
    def eci_to_ecef(p: Vec3, t: float) -> Vec3:
        return _rot_z(p, -OMEGA_EARTH * t)

    @staticmethod
    def ecef_to_geodetic(p: Vec3) -> tuple[float, float, float]:
        x, y, z = p
        r = _norm(p)
        lat = math.degrees(math.asin(max(-1.0, min(1.0, z / r))))
        lon = math.degrees(math.atan2(y, x))
        alt = r - R_EARTH
        return lat, lon, alt

    # ── 食判定（円筒影モデル）─────────────────────────
    def in_eclipse(self, t: float) -> bool:
        p = self.position_eci(t)
        s = self.sun_eci(t)
        proj = _dot(p, s)
        if proj >= 0:
            return False                     # 太陽側
        perp = (p[0] - proj * s[0], p[1] - proj * s[1], p[2] - proj * s[2])
        return _norm(perp) < R_EARTH         # 影の円筒内

    # ── β角（軌道面と太陽のなす角）─────────────────────
    def beta_angle_deg(self, t: float) -> float:
        s = self.sun_eci(t)
        nrm = self.normal_eci(t)
        return math.degrees(math.asin(max(-1.0, min(1.0, _dot(s, nrm)))))

    # ── 地上局位置 (ECEF) ─────────────────────────────
    @staticmethod
    def station_ecef(lat_deg: float, lon_deg: float) -> Vec3:
        lat, lon = math.radians(lat_deg), math.radians(lon_deg)
        return (
            R_EARTH * math.cos(lat) * math.cos(lon),
            R_EARTH * math.cos(lat) * math.sin(lon),
            R_EARTH * math.sin(lat),
        )

    # ── 地上局仰角 ────────────────────────────────────
    def elevation_deg(self, sat_ecef: Vec3, st_lat: float, st_lon: float) -> float:
        st = self.station_ecef(st_lat, st_lon)
        rho = (sat_ecef[0] - st[0], sat_ecef[1] - st[1], sat_ecef[2] - st[2])
        up = _unit(st)
        el = math.asin(max(-1.0, min(1.0, _dot(_unit(rho), up))))
        return math.degrees(el)

    # ── 地上局方位角 (N=0°, E=90°, 時計回り) ──────────
    def azimuth_deg(self, sat_ecef: Vec3, st_lat: float, st_lon: float) -> float:
        lat = math.radians(st_lat)
        lon = math.radians(st_lon)
        st = self.station_ecef(st_lat, st_lon)
        rho_u = _unit((
            sat_ecef[0] - st[0],
            sat_ecef[1] - st[1],
            sat_ecef[2] - st[2],
        ))
        # NEU (North-East-Up) 局所座標軸
        north = (
            -math.sin(lat) * math.cos(lon),
            -math.sin(lat) * math.sin(lon),
            math.cos(lat),
        )
        east = (-math.sin(lon), math.cos(lon), 0.0)
        n_comp = _dot(rho_u, north)
        e_comp = _dot(rho_u, east)
        return math.degrees(math.atan2(e_comp, n_comp)) % 360.0

    # ── 将来パス予測 ─────────────────────────────────
    def predict_passes(
        self,
        stations: dict,
        t_start: float,
        n_orbits: int = 5,
        step_s: float = 20.0,
    ) -> list[PredictedPass]:
        """将来 n_orbits 周回分の地上局可視ウィンドウを予測する.

        Args:
            stations: {code: {lat, lon, min_el}} 地上局辞書
            t_start: 予測開始シミュレーション時刻 [sim秒]
            n_orbits: 予測周回数
            step_s: タイムステップ [sim秒]

        Returns:
            PredictedPass のリスト (t_aos 昇順)
        """
        t_end = t_start + n_orbits * self.period_s
        results: list[PredictedPass] = []

        for code, meta in stations.items():
            in_pass = False
            p_state: dict | None = None
            t = t_start

            while t <= t_end:
                p_eci = self.position_eci(t)
                p_ecef = self.eci_to_ecef(p_eci, t)
                el = self.elevation_deg(p_ecef, meta["lat"], meta["lon"])
                az = self.azimuth_deg(p_ecef, meta["lat"], meta["lon"])

                if el >= meta["min_el"]:
                    if not in_pass:
                        in_pass = True
                        p_state = {
                            "t_aos": t, "t_los": t,
                            "max_el": el, "max_az": az,
                            "rise_az": az, "set_az": az,
                        }
                    else:
                        p_state["t_los"] = t
                        p_state["set_az"] = az
                        if el > p_state["max_el"]:
                            p_state["max_el"] = el
                            p_state["max_az"] = az
                else:
                    if in_pass and p_state:
                        results.append(PredictedPass(
                            station=code,
                            t_aos=p_state["t_aos"],
                            t_los=p_state["t_los"],
                            max_el=p_state["max_el"],
                            rise_az=p_state["rise_az"],
                            max_az=p_state["max_az"],
                            set_az=p_state["set_az"],
                            duration_s=p_state["t_los"] - p_state["t_aos"],
                        ))
                    in_pass = False
                    p_state = None

                t += step_s

            # 予測期間末まで可視だった場合
            if in_pass and p_state:
                results.append(PredictedPass(
                    station=code,
                    t_aos=p_state["t_aos"],
                    t_los=p_state["t_los"],
                    max_el=p_state["max_el"],
                    rise_az=p_state["rise_az"],
                    max_az=p_state["max_az"],
                    set_az=p_state["set_az"],
                    duration_s=p_state["t_los"] - p_state["t_aos"],
                ))

        results.sort(key=lambda pp: pp.t_aos)
        return results
