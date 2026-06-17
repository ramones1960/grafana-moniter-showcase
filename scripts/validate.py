#!/usr/bin/env python3
"""リポジトリ構成の静的検証（Dockerデーモン不要）.

- すべての YAML が parse できる
- すべての Grafana ダッシュボード JSON が妥当
- simulator の Python が compile できる
"""
import glob
import json
import os
import py_compile
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
errors = []


def check_yaml():
    for path in glob.glob(os.path.join(ROOT, "stack", "**", "*.yml"),
                          recursive=True) + glob.glob(
            os.path.join(ROOT, "stack", "**", "*.yaml"), recursive=True):
        try:
            with open(path) as f:
                yaml.safe_load(f)
        except Exception as e:  # noqa: BLE001
            errors.append(f"YAML {path}: {e}")


def check_dashboards():
    files = glob.glob(os.path.join(ROOT, "stack", "grafana", "dashboards",
                                   "*.json"))
    if not files:
        errors.append("ダッシュボード JSON が見つかりません")
    for path in files:
        try:
            d = json.load(open(path))
            assert d.get("uid"), "uid 欠落"
            assert d.get("panels"), "panels 欠落"
            for p in d["panels"]:
                assert "type" in p and "gridPos" in p, "panel 不正"
        except Exception as e:  # noqa: BLE001
            errors.append(f"DASHBOARD {path}: {e}")


def check_python():
    for path in glob.glob(os.path.join(ROOT, "stack", "simulator", "*.py")):
        try:
            py_compile.compile(path, doraise=True)
        except Exception as e:  # noqa: BLE001
            errors.append(f"PY {path}: {e}")


def main():
    check_yaml()
    check_dashboards()
    check_python()
    if errors:
        print("検証 NG:")
        for e in errors:
            print("  -", e)
        sys.exit(1)
    print("検証 OK: YAML / dashboards / python すべて妥当")


if __name__ == "__main__":
    main()
