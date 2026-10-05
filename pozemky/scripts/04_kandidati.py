"""Krok 2a: kandidátne LV so SPF zoznamu pre zvolené územie (okresy alebo koridor medzi dvoma mestami).

Bez ZBGIS (výmera, druh, intravilán) sa dá z SPF zoznamu zistiť len: k.ú., LV, mená nezistených
vlastníkov a ich počet na LV. Skript to pripraví ako CSV + JSON pre webovú stránku.

Spustenie:
    python scripts/04_kandidati.py --okresy Nitra Topoľčany --tag nr_to
    python scripts/04_kandidati.py --medzi Nitra Topoľčany --sirka 6000 --tag nr_to   # koridor okolo osi
    python scripts/04_kandidati.py --ku 820903 866539 --tag chrabrany_urmince

Výstupy: data/kandidati_<tag>.csv (všetky LV), data/kandidati_<tag>_ku.csv (súhrn k.ú.),
         web/kandidati_<tag>.json (LV s >= --min-mien menami, pre stránku)
"""
import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

# doplňujúci údaj k menu: č.d. = číslo denníka pozemkovej knihy (nie adresa), nar., PSČ, bytom, manž., r. (rodné meno)
RE_UDAJ = re.compile(r"č\.?\s?d\.?\s?\d|čd\.?\s?\d|PSČ|\bnar\.|bytom|manž|\br\.\s?[A-ZÁ-Ž]|rod\.", re.I)
RE_UMRTIE = re.compile(r"zom\.|úmrti|zomrel|\+\s?\d{1,2}\.", re.I)
RE_SPF = re.compile(r"\bSPF\b")


def ocisti_meno(s: str) -> str:
    """SPF export opakuje poznámku: 'Meno (pozn.) D:(pozn.)' alebo 'Meno, (pozn.) pozn.' -> 'Meno (pozn.)'."""
    s = re.sub(r"\s+", " ", s).strip()
    i = s.find("(")
    if i < 0:
        return s
    hl, j = 0, i
    while j < len(s):
        hl += s[j] == "("
        hl -= s[j] == ")"
        if hl == 0:
            break
        j += 1
    if j >= len(s):
        return s
    pozn = s[i + 1:j]
    zvysok = s[j + 1:].strip()
    norm = lambda t: re.sub(r"[\s|]+", " ", re.sub(r"^D:", "", t).strip().strip("()")).strip()
    if zvysok and norm(zvysok) == norm(pozn):
        return s[: j + 1]
    return s


def vyber_ku(ku: pd.DataFrame, a) -> pd.DataFrame:
    if a.ku:
        return ku[ku.ku_kod.isin(a.ku)].copy()
    if a.medzi:
        p = {n: ku[(ku.ku_nazov_gn == n) | (ku.obec == n)].sort_values("ku_kod").iloc[0] for n in a.medzi}
        A = np.array([p[a.medzi[0]].x_jtsk, p[a.medzi[0]].y_jtsk])
        B = np.array([p[a.medzi[1]].x_jtsk, p[a.medzi[1]].y_jtsk])
        d = B - A
        L = np.linalg.norm(d)
        u = d / L
        P = ku[["x_jtsk", "y_jtsk"]].to_numpy() - A
        ku = ku.assign(os_t=P @ u, os_dist=np.abs(P[:, 0] * u[1] - P[:, 1] * u[0]))
        sel = ku[(ku.os_t >= -a.sirka / 2) & (ku.os_t <= L + a.sirka / 2) & (ku.os_dist <= a.sirka)]
        if a.okresy:
            sel = sel[sel.okres.isin(a.okresy)]
        return sel.sort_values("os_t").copy()
    return ku[ku.okres.isin(a.okresy)].copy()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--okresy", nargs="*", default=[])
    ap.add_argument("--medzi", nargs=2, metavar=("MESTO_A", "MESTO_B"))
    ap.add_argument("--sirka", type=float, default=6000, help="max. vzdialenosť stredu k.ú. od osi [m]")
    ap.add_argument("--ku", nargs="*", type=int)
    ap.add_argument("--min-mien", type=int, default=2, help="min. počet nezistených mien na LV pre JSON")
    ap.add_argument("--tag", required=True)
    a = ap.parse_args()

    ku = pd.read_csv(ROOT / "data" / "ciselnik_ku.csv")
    sel = vyber_ku(ku, a)
    print(f"k.ú.: {len(sel)}")

    spf = pd.read_parquet(ROOT / "data" / "spf_nezisteni.parquet")
    s = spf[spf.ku_kod.isin(sel.ku_kod)].copy()
    s["meno_c"] = s["meno"].map(ocisti_meno)
    s["udaj"] = s["meno_c"].str.contains(RE_UDAJ)
    s["umrtie"] = s["meno_c"].str.contains(RE_UMRTIE)
    s["spf"] = s["meno_c"].str.contains(RE_SPF)

    lv = (s.groupby(["ku_kod", "lv"])
            .agg(pocet_nezist=("meno_c", "size"),
                 s_udajom=("udaj", "sum"),
                 s_umrtim=("umrtie", "sum"),
                 spf_pozn=("spf", "sum"),
                 mena=("meno_c", lambda x: " | ".join(x)))
            .reset_index())
    lv = lv.merge(sel[["ku_kod", "ku_nazov_gn", "obec", "okres"] + (["os_dist"] if "os_dist" in sel else [])],
                  on="ku_kod")
    lv = lv.rename(columns={"ku_nazov_gn": "ku_nazov"}).sort_values(["pocet_nezist", "ku_kod", "lv"],
                                                                    ascending=[False, True, True])
    lv.to_csv(ROOT / "data" / f"kandidati_{a.tag}.csv", index=False)

    kus = (lv.groupby(["ku_kod", "ku_nazov", "obec", "okres"])
             .agg(lv=("lv", "size"), mien=("pocet_nezist", "sum"),
                  lv_2plus=("pocet_nezist", lambda x: int((x >= 2).sum())),
                  lv_3_8=("pocet_nezist", lambda x: int(x.between(3, 8).sum())),
                  lv_9plus=("pocet_nezist", lambda x: int((x >= 9).sum())))
             .reset_index())
    kus.to_csv(ROOT / "data" / f"kandidati_{a.tag}_ku.csv", index=False)
    print(kus.to_string(index=False))
    print(f"\nLV spolu: {len(lv)}, s >=2 menami: {(lv.pocet_nezist >= 2).sum()}, "
          f"3–8 mien: {lv.pocet_nezist.between(3, 8).sum()}, >=9: {(lv.pocet_nezist >= 9).sum()}")

    web = lv[lv.pocet_nezist >= a.min_mien]
    rows = [[int(r.ku_kod), r.ku_nazov, r.okres, int(r.lv), int(r.pocet_nezist), int(r.s_udajom),
             int(r.s_umrtim), r.mena.split(" | ")] for r in web.itertuples()]
    out = {"tag": a.tag, "ku": kus.to_dict(orient="records"), "lv": rows,
           "pocet_lv_spolu": int(len(lv)), "pocet_mien_spolu": int(lv.pocet_nezist.sum())}
    (ROOT / "web").mkdir(exist_ok=True)
    (ROOT / "web" / f"kandidati_{a.tag}.json").write_text(json.dumps(out, ensure_ascii=False))
    print(f"JSON: {len(rows)} LV")


if __name__ == "__main__":
    main()
