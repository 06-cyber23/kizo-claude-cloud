"""Krok 1.1: stiahne 7 CSV 'Nezistení vlastníci k 30.06.2026' zo SPF a spojí ich.

Stĺpce: ku_nazov, ku_kod, lv, meno
Spustenie: python scripts/01_spf_stiahni_spoj.py [--bez-stahovania]
"""
import sys
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
BASE = "https://pozfond.sk/wp-content/uploads/2026/07/{}-Nezisteni-vlastnici-k-30.06.2026.csv"
CASTI = ["A_G", "H_J", "K_L", "M_O", "P_R", "S_U", "V_Z"]


def stiahni():
    RAW.mkdir(parents=True, exist_ok=True)
    for c in CASTI:
        r = requests.get(BASE.format(c), headers={"User-Agent": "Mozilla/5.0"}, timeout=300)
        r.raise_for_status()
        (RAW / f"{c}.csv").write_bytes(r.content)
        print(c, len(r.content), "B")


def spoj() -> pd.DataFrame:
    frames = []
    for c in CASTI:
        # meno môže obsahovať ';' aj úvodzovky -> delíme len prvé 3 bodkočiarky
        with open(RAW / f"{c}.csv", encoding="utf-8-sig", newline="") as f:
            next(f)  # hlavička
            rows = [ln.rstrip("\r\n").split(";", 3) for ln in f if ln.strip()]
        df = pd.DataFrame(rows, columns=["ku_nazov", "ku_kod", "lv", "meno"])
        df["subor"] = c
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    for col in ["ku_nazov", "ku_kod", "lv", "meno"]:
        df[col] = df[col].str.strip()
    df["ku_kod"] = pd.to_numeric(df["ku_kod"], errors="coerce").astype("Int64")
    df["lv"] = pd.to_numeric(df["lv"], errors="coerce").astype("Int64")
    return df


if __name__ == "__main__":
    if "--bez-stahovania" not in sys.argv:
        stiahni()
    df = spoj()
    df.to_parquet(ROOT / "data" / "spf_nezisteni.parquet", index=False, compression="zstd")
    print("riadkov:", len(df))
    print("unikátnych LV (k.ú.+LV):", df[["ku_kod", "lv"]].drop_duplicates().shape[0])
    print("k.ú.:", df["ku_kod"].nunique())
    print("chybný ku_kod/lv:", df["ku_kod"].isna().sum(), df["lv"].isna().sum())
