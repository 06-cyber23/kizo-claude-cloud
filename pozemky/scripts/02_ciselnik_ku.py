"""Krok 1.2: číselník k.ú. -> obec -> okres -> kraj (GKÚ, geografické názvy, GNKU.csv)
a napojenie na SPF zoznam.

Zdroj: https://www.skgeodesy.sk/files/gku/produkty-sluzby/na-stiahnutie/gn_csv.zip (CC-BY 4.0)
Výstupy: data/ciselnik_ku.csv, data/spf_ku_suhrn.csv
Spustenie: python scripts/02_ciselnik_ku.py [--bez-stahovania]
"""
import io
import sys
import zipfile
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
URL = "https://www.skgeodesy.sk/files/gku/produkty-sluzby/na-stiahnutie/gn_csv.zip"


def nacitaj_gnku() -> pd.DataFrame:
    zp = RAW / "gn_csv.zip"
    if "--bez-stahovania" not in sys.argv or not zp.exists():
        r = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=300)
        r.raise_for_status()
        zp.write_bytes(r.content)
    with zipfile.ZipFile(zp) as z:
        raw = z.read("GNKU.csv")
    df = pd.read_csv(io.BytesIO(raw), sep=";", encoding="cp1250")
    df = df.rename(columns={"IDN5": "ku_kod", "NM5": "ku_nazov_gn", "IDN4": "obec_kod",
                            "NM4": "obec", "IDN3": "okres_kod", "NM3": "okres",
                            "IDN2": "kraj_kod", "NM2": "kraj",
                            "POINT_X": "x_jtsk", "POINT_Y": "y_jtsk"})
    return df


if __name__ == "__main__":
    ku = nacitaj_gnku()
    ku.to_csv(ROOT / "data" / "ciselnik_ku.csv", index=False)
    print("k.ú. v číselníku:", len(ku), "okresov:", ku.okres.nunique(), "krajov:", ku.kraj.nunique())

    spf = pd.read_parquet(ROOT / "data" / "spf_nezisteni.parquet")
    s = (spf.groupby(["ku_kod", "ku_nazov"])
            .agg(zaznamov=("lv", "size"), lv_pocet=("lv", "nunique")).reset_index())
    m = s.merge(ku, on="ku_kod", how="left")
    nenapojene = m[m.obec.isna()]
    print("SPF k.ú.:", len(s), "napojených:", len(s) - len(nenapojene), "nenapojených:", len(nenapojene))
    if len(nenapojene):
        print(nenapojene[["ku_kod", "ku_nazov", "zaznamov"]].to_string(index=False))
    m.to_csv(ROOT / "data" / "spf_ku_suhrn.csv", index=False)
    po = (m.groupby(["kraj", "okres"]).agg(ku=("ku_kod", "size"), zaznamov=("zaznamov", "sum"),
                                           lv=("lv_pocet", "sum"))
            .sort_values("zaznamov", ascending=False))
    po.to_csv(ROOT / "data" / "spf_okres_suhrn.csv")
    print(po.head(20).to_string())
