"""簡易軌道伝播モデル.

円軌道を仮定し、経過(シミュレーション)秒から
直下点 (lat/lon)、高度、食(eclipse)、β角、地上局仰角を求める。
天文学的厳密性より、宇宙運用ダッシュボードを成立させる物理的妥当性を優先。
"""
from __future__ import annotations

import math
from dataclasses import dataclass

MU = 398600.4418            # 地球重力定数 [km^3/s^2]
R_EARTH = 6371.0            # 地球平均半径 [km]
OMEGA_EARTH = 7.2921159e-5  # 地球自転角速度 [rad/s]
OBLIQUITY = math.radians(23.439)  # 黄道傾斜角
YEAR_SEC = 365.25 * 86400.0

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
    visible: bool


class Orbit:
    def __init__(self, altitude_km: float, inclination_deg: float, raan_deg: float):
        self.a = R_EARTH + altitude_km
        self.incl = math.radians(inclination_deg)
        self.raan = math.radians(raan_deg)
        self.n = math.sqrt(MU / self.a ** 3)   # 平均運動 [rad/s]
        self.period_s = 2 * math.pi / self.n

    # ── 衛星位置 (ECI) ────────────────────────────────
    def position_eci(self, t: float) -> Vec3:
        nu = self.n * t                      # 円軌道: 真近点角 = 平均近点角
        r_pf: Vec3 = (self.a * math.cos(nu), self.a * math.sin(nu), 0.0)
        return _rot_z(_rot_x(r_pf, self.incl), self.raan)

    def normal_eci(self) -> Vec3:
        return _unit(_rot_z(_rot_x((0.0, 0.0, 1.0), self.incl), self.raan))

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
        nrm = self.normal_eci()
        return math.degrees(math.asin(max(-1.0, min(1.0, _dot(s, nrm)))))

    # ── 地上局仰角 ────────────────────────────────────
    @staticmethod
    def station_ecef(lat_deg: float, lon_deg: float) -> Vec3:
        lat, lon = math.radians(lat_deg), math.radians(lon_deg)
        return (
            R_EARTH * math.cos(lat) * math.cos(lon),
            R_EARTH * math.cos(lat) * math.sin(lon),
            R_EARTH * math.sin(lat),
        )

    def elevation_deg(self, sat_ecef: Vec3, st_lat: float, st_lon: float) -> float:
        st = self.station_ecef(st_lat, st_lon)
        rho = (sat_ecef[0] - st[0], sat_ecef[1] - st[1], sat_ecef[2] - st[2])
        up = _unit(st)
        el = math.asin(max(-1.0, min(1.0, _dot(_unit(rho), up))))
        return math.degrees(el)
