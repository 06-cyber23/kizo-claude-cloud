"""Krok 2d: zostavy SPF „Z126 Neprenajaté pozemky v správe a nakladaní SPF“ (PDF po k.ú.) → tabuľka
parcela C + výmera + druh pozemku + LV + intravilán + výmera podielov nezistených vlastníkov,
spojená s menami zo SPF zoznamu (k.ú. + LV) a s geometriou z INSPIRE (k.ú. + parcela C).

Zdroj: https://pozfond.sk/zoznam-pozemkov-na-prenajom-archiv-2-4-2026/ (3 559 PDF, stav 26.02.2026),
URL vzor https://pozfond.sk/wp-content/uploads/uzemneplany/{Okres}_{Obec}_{KU}.pdf (bez diakritiky, '-' za medzery).
Voliteľne Z166 „pozemky s končiacimi nájomnými zmluvami 2026“ (…/neprenajate-pozemky/…, stav 27.03.2026).
Pokrytie: len NEPRENAJATÉ pozemky v nakladaní SPF (~1–2 % LV zo zoznamu); riadky s LV=0 = C-parcela bez LV
(vlastníctvo je evidované na E-parcelách) – k nim sa LV z verejných zdrojov priradiť nedá.

Spustenie:
    python scripts/07_spf_z126.py --tag nr_to
Vstupy: data/raw/spf_z126/{ku_kod}.pdf (stiahnuté podľa data/raw/z126_urls.csv), data/raw/spf_z166/*.pdf,
        data/kandidati_<tag>.csv (mená na LV), data/parcely_<tag>.parquet (geometria, intravilán ZUOB)
Výstupy: data/z126_<tag>.csv (1 riadok = 1 parcela zo zostavy), data/z126_<tag>_lv.csv (1 riadok = 1 LV),
         web/z126_<tag>.json (pre stránku)
"""
import argparse
import json
import re
import subprocess
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DRUHY = {2: "orná pôda", 3: "chmeľnica", 4: "vinica", 5: "záhrada", 6: "ovocný sad", 7: "trvalý trávny porast",
         10: "lesný pozemok", 11: "vodná plocha", 13: "zastavaná plocha a nádvorie", 14: "ostatná plocha"}
# Z126: Okres Obec K.ú. Parcela Výmera Druh LV Um.poz. SR-SPF NV-SPF (v správe) SR-SPF NV-SPF Spolu (neprenajaté) = 5 čísel
# Z166: Okres Obec K.ú. Parcela Výmera Druh I/E LV Prenajímaná SR-SPF NV-SPF Spolu = 4 čísla
R_RIADOK = re.compile(r"^\s*(\S+)\s+(\S+)\s+(\S.*?\S)\s+(\d+(?:/\d+)?)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)((?:\s+[\d.]+){4,5})\s*$")


def pdf_text(p: Path) -> str:
    return subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True, check=True).stdout


def parse(p: Path, ku_kod: int, zdroj: str) -> list[dict]:
    rows = []
    datum = None
    for line in pdf_text(p).splitlines():
        if datum is None:
            md = re.search(r"\b(\d{2}\.\d{2}\.\d{4})\b", line)
            if md and ("ku dňu" in line or "Z1" in line):
                datum = md.group(1)
        m = R_RIADOK.match(line)
        if not m:
            continue
        g = m.groups()
        cisla = [float(x) for x in g[8].split()]
        if zdroj == "Z126":
            lv, um = int(g[6]), g[7]
            if len(cisla) != 5 or um not in ("1", "2"):
                continue
            nv_sprava, sr_nepren, nv_nepren, spolu = cisla[1], cisla[2], cisla[3], cisla[4]
            prenaj = None
        else:
            um, lv = g[6], int(g[7])
            if len(cisla) != 4 or um not in ("1", "2"):
                continue
            prenaj, sr_nepren, nv_nepren, spolu = cisla
            nv_sprava = nv_nepren
        rows.append(dict(ku_kod=ku_kod, zdroj=zdroj, datum=datum, okres_pdf=g[0], ku_nazov_pdf=g[2],
                         parcela=g[3], vymera_m2=int(g[4]), druh_kod=int(g[5]), druh=DRUHY.get(int(g[5]), str(g[5])),
                         intravilan_spf=um == "1", lv=lv, prenajimana_m2=prenaj, sr_spf_m2=sr_nepren,
                         nv_spf_m2=nv_nepren, nv_sprava_m2=nv_sprava, spolu_spf_m2=spolu))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    a = ap.parse_args()

    urls = pd.read_csv(ROOT / "data" / "raw" / "z126_urls.csv")
    rows = []
    for r in urls.itertuples():
        p = ROOT / "data" / "raw" / "spf_z126" / f"{r.ku_kod}.pdf"
        if p.exists():
            rows += parse(p, int(r.ku_kod), "Z126")
    ku = pd.read_csv(ROOT / "data" / "ciselnik_ku.csv")[["ku_kod", "ku_nazov_gn", "obec", "okres"]]
    # Z166: názov súboru Okres_Obec_KU.pdf -> k.ú. cez slug
    import unicodedata

    def slug(s):
        s = "".join(c for c in unicodedata.normalize("NFD", str(s)) if unicodedata.category(c) != "Mn")
        return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    ku["slug"] = ku.okres.map(slug) + "_" + ku.obec.map(slug) + "_" + ku.ku_nazov_gn.map(slug)
    for p in sorted((ROOT / "data" / "raw" / "spf_z166").glob("*.pdf")):
        hit = ku[ku.slug == p.stem.lower()]
        if len(hit) == 1:
            rows += parse(p, int(hit.ku_kod.iloc[0]), "Z166")
    z = pd.DataFrame(rows)
    if z.empty:
        raise SystemExit("žiadne riadky – chýbajú PDF alebo sa zmenil formát")
    z = z.drop_duplicates(["ku_kod", "parcela", "lv", "zdroj"])
    z = z[z.ku_kod.isin(set(urls.ku_kod))]  # len k.ú. z koridoru (Z166 má aj iné)
    z["nv_podiel"] = (z.nv_spf_m2 / z.vymera_m2).round(3)
    z = z.merge(ku[["ku_kod", "ku_nazov_gn", "okres"]].rename(columns={"ku_nazov_gn": "ku_nazov"}), on="ku_kod", how="left")

    # geometria + ZUOB z INSPIRE (register C)
    par = pd.read_parquet(ROOT / "data" / f"parcely_{a.tag}.parquet",
                          columns=["ku_kod", "register", "parcela", "vymera_m2", "intravilan", "lon", "lat"])
    par = par[par.register == "C"].drop_duplicates(["ku_kod", "parcela"]).rename(
        columns={"vymera_m2": "vymera_inspire_m2", "intravilan": "intravilan_zuob"})
    z = z.merge(par[["ku_kod", "parcela", "vymera_inspire_m2", "intravilan_zuob", "lon", "lat"]], on=["ku_kod", "parcela"], how="left")

    # mená zo SPF zoznamu
    lv = pd.read_csv(ROOT / "data" / f"kandidati_{a.tag}.csv", dtype={"mena": str})[["ku_kod", "lv", "pocet_nezist", "mena"]]
    z = z.merge(lv, on=["ku_kod", "lv"], how="left")
    z["v_spf_zozname"] = z.pocet_nezist.notna()
    z.to_csv(ROOT / "data" / f"z126_{a.tag}.csv", index=False)

    print(f"riadkov: {len(z)} | k.ú.: {z.ku_kod.nunique()} | LV>0: {(z.lv > 0).sum()} | LV=0: {(z.lv == 0).sum()}")
    print(f"LV>0 v SPF zozname: {z[z.lv > 0].v_spf_zozname.sum()} riadkov / {z[(z.lv > 0) & z.v_spf_zozname].groupby(['ku_kod','lv']).ngroups} LV")
    print(f"intravilán (SPF): {z.intravilan_spf.sum()} | zhoda SPF um.poz. vs ZUOB: "
          f"{(z.intravilan_spf == z.intravilan_zuob)[z.intravilan_zuob.notna()].mean():.1%} | geometria nájdená: {z.lon.notna().mean():.1%}")
    print(f"výmera uvedená = INSPIRE: {(z.vymera_m2 == z.vymera_inspire_m2)[z.vymera_inspire_m2.notna()].mean():.1%}")

    g = z[z.lv > 0]
    lvt = (g.groupby(["ku_kod", "ku_nazov", "okres", "lv"])
             .agg(parciel=("parcela", "size"), parcely=("parcela", lambda s: ", ".join(s)),
                  vymera_m2=("vymera_m2", "sum"), nv_spf_m2=("nv_spf_m2", "sum"),
                  druhy=("druh", lambda s: ", ".join(sorted(set(s)))),
                  intravilan=("intravilan_spf", "any"), zdroj=("zdroj", lambda s: "+".join(sorted(set(s)))),
                  pocet_nezist=("pocet_nezist", "first"), mena=("mena", "first"))
             .reset_index())
    lvt["nv_podiel"] = (lvt.nv_spf_m2 / lvt.vymera_m2).round(3)
    lvt["v_spf"] = lvt.pocet_nezist.notna()
    lvt = lvt.sort_values(["v_spf", "intravilan", "vymera_m2"], ascending=[False, False, False])
    lvt.to_csv(ROOT / "data" / f"z126_{a.tag}_lv.csv", index=False)
    print(f"LV spolu: {len(lvt)} | v SPF zozname: {lvt.pocet_nezist.notna().sum()} | intravilán: {lvt.intravilan.sum()}")
    print(lvt.head(15)[["ku_nazov", "lv", "parcely", "vymera_m2", "druhy", "intravilan", "nv_podiel", "pocet_nezist"]].to_string(index=False))

    out = {"tag": a.tag, "datum": sorted(z.datum.dropna().unique().tolist()),
           "lv": [[int(r.ku_kod), r.ku_nazov, r.okres, int(r.lv), r.parcely, int(r.vymera_m2), r.druhy, bool(r.intravilan),
                   float(r.nv_podiel), int(r.pocet_nezist) if pd.notna(r.pocet_nezist) else 0,
                   r.mena.split(" | ") if isinstance(r.mena, str) else [], r.zdroj] for r in lvt.itertuples()],
           "bez_lv": [[int(r.ku_kod), r.ku_nazov, r.parcela, int(r.vymera_m2), r.druh, bool(r.intravilan_spf), float(r.nv_podiel),
                       r.lon if pd.notna(r.lon) else None, r.lat if pd.notna(r.lat) else None]
                      for r in z[z.lv == 0].sort_values("nv_spf_m2", ascending=False).itertuples()]}
    (ROOT / "web" / f"z126_{a.tag}.json").write_text(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
