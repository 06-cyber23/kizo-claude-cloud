"""Krok 1.3: overenie, či verejná ZBGIS/ESKN REST služba vracia pri parcelách C a E
číslo LV, výmeru a druh pozemku – pre JEDNO katastrálne územie – a spojenie so SPF zoznamom.

POZOR: servery *.skgeodesy.sk z cloudu (zahraničná IP) neodpovedajú. Spúšťaj z notebooku
so slovenským pripojením.

Spustenie:
    python scripts/03_zbgis_overenie.py                 # default k.ú. Papradno (845337)
    python scripts/03_zbgis_overenie.py --ku 845337
    python scripts/03_zbgis_overenie.py --ku 845337 --len-schema   # iba vypíše atribúty vrstiev

Čo robí:
 1. Stiahne metadáta vrstiev parcels_c_view a parcels_e_view (ArcGIS REST, ?f=json) a vypíše
    zoznam atribútov -> data/zbgis/schema_<reg>.json. Z toho je vidno, či je tam LV/druh/výmera.
 2. Stiahne atribúty (bez geometrie) všetkých parciel C a E v danom k.ú. (stránkovane,
    s pauzou medzi požiadavkami) -> data/zbgis/parcely_<ku>_<reg>.csv
 3. Ak sa nájde stĺpec s číslom LV, spojí so SPF (k.ú. + LV) a uloží
    data/zbgis/spoj_<ku>.csv a .html (LV, mená, parcely, výmera spolu, druh pozemku).
 4. Doplnkovo skúsi INSPIRE OGC API Features (cp / cp_uo) – tam LV ani druh pozemku
    podľa špecifikácie INSPIRE nie sú, len číslo parcely, výmera a geometria.

Názvy stĺpcov sa zisťujú automaticky; ak treba, dajú sa vynútiť:
    --pole-ku CADASTRAL_UNIT_CODE --pole-lv FOLIO_NO --pole-vymera AREA --pole-druh LAND_USE
"""
import argparse
import json
import re
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "zbgis"
ESKN = "https://kataster.skgeodesy.sk/eskn/rest/services/VRM/parcels_{reg}_view/MapServer/0"
INSPIRE = {"c": "https://inspirews.skgeodesy.sk/geoserver/cp/ogc/features/v1",
           "e": "https://inspirews.skgeodesy.sk/geoserver/cp_uo/ogc/features/v1"}
HDR = {"User-Agent": "pozemky-overenie/0.1 (jednorazove overenie 1 k.u.)"}
PAUZA = 1.0  # s medzi požiadavkami

# Druhy pozemkov podľa vyhlášky ÚGKK SR č. 461/2009 Z. z. (príloha, kódy druhov pozemkov)
DRUHY = {2: "orná pôda", 3: "chmeľnica", 4: "vinica", 5: "záhrada", 6: "ovocný sad",
         7: "trvalý trávny porast", 10: "lesný pozemok", 11: "vodná plocha",
         13: "zastavaná plocha a nádvorie", 14: "ostatná plocha"}

VZORY = {
    "ku": r"CADASTRAL_UNIT_CODE|CADASTRAL.*CODE|^KU$|KU_?KOD|KOD_?KU|KATUZ|ICUTJ",
    "lv": r"FOLIO|^LV$|CIS.*LV|LV_?(NO|CIS|CISLO)|LIST.*VLAST|OWNERSHIP_SHEET",
    "vymera": r"^AREA$|AREA_?(VALUE|M2|OFFICIAL)?$|VYMERA",
    "druh": r"LAND_?USE|LAND_?TYPE|DRUH|PARCEL_TYPE|KIND",
    "cislo": r"PARCEL_NUMBER|PARCEL_?(NO|NUM)|CISLO_?PARC",
}


def get(url, params=None):
    r = requests.get(url, params=params, headers=HDR, timeout=60)
    r.raise_for_status()
    time.sleep(PAUZA)
    return r.json()


def najdi(fields, kluc, vynutene=None):
    if vynutene:
        return vynutene
    for f in fields:
        if re.search(VZORY[kluc], f["name"], re.I) or re.search(VZORY[kluc], f.get("alias") or "", re.I):
            return f["name"]
    return None


def schema(reg):
    meta = get(ESKN.format(reg=reg), {"f": "json"})
    (OUT / f"schema_{reg}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    print(f"\n== parcels_{reg}_view: {meta.get('name')} | maxRecordCount={meta.get('maxRecordCount')}")
    for f in meta.get("fields", []):
        print(f"   {f['name']:<32} {str(f.get('alias')):<32} {f['type']}")
    return meta


def parcely(reg, meta, ku, a):
    fields = meta.get("fields", [])
    pole = {k: najdi(fields, k, getattr(a, f"pole_{k}", None)) for k in VZORY}
    print(f"   rozpoznané stĺpce ({reg.upper()}): {pole}")
    if not pole["ku"]:
        print("   !! nenašiel sa stĺpec s kódom k.ú. – zadaj --pole-ku podľa výpisu vyššie")
        return None, pole
    url = ESKN.format(reg=reg) + "/query"
    hodnota = ku if any(f["name"] == pole["ku"] and "String" not in f["type"] for f in fields) else f"'{ku}'"
    where = f"{pole['ku']}={hodnota}"
    ids = get(url, {"where": where, "returnIdsOnly": "true", "f": "json"}).get("objectIds") or []
    print(f"   parciel {reg.upper()} v k.ú.: {len(ids)}")
    krok = min(int(meta.get("maxRecordCount") or 1000), 1000)
    rows = []
    for i in range(0, len(ids), krok):
        chunk = ids[i:i + krok]
        d = get(url, {"objectIds": ",".join(map(str, chunk)), "outFields": "*",
                      "returnGeometry": "false", "f": "json"})
        rows += [ft["attributes"] for ft in d.get("features", [])]
        print(f"   {len(rows)}/{len(ids)}", end="\r")
    df = pd.DataFrame(rows)
    df.to_csv(OUT / f"parcely_{ku}_{reg}.csv", index=False)
    print()
    return df, pole


def inspire_test(reg, ku):
    """Iba overenie atribútov INSPIRE (prvých 5 parciel v k.ú.)."""
    try:
        d = get(f"{INSPIRE[reg]}/collections/CP.CadastralParcel/items",
                {"limit": 5, "filter-lang": "cql-text",
                 "filter": f"nationalCadastralReference LIKE '{ku}%'", "f": "json"})
        props = [f.get("properties", {}) for f in d.get("features", [])]
        print(f"\n== INSPIRE {reg.upper()}: atribúty: {sorted(props[0].keys()) if props else 'žiadne záznamy'}")
        for p in props[:3]:
            print("  ", p)
    except Exception as e:  # noqa: BLE001
        print(f"\n== INSPIRE {reg.upper()}: chyba {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ku", type=int, default=845337)
    ap.add_argument("--len-schema", action="store_true")
    for k in VZORY:
        ap.add_argument(f"--pole-{k}")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    try:
        metas = {reg: schema(reg) for reg in ("c", "e")}
    except requests.RequestException as e:
        raise SystemExit(f"ZBGIS/ESKN služba nedostupná ({e}). Spusti zo slovenského pripojenia.")
    for reg in ("c", "e"):
        inspire_test(reg, a.ku)
    if a.len_schema:
        return

    spf = pd.read_parquet(ROOT / "data" / "spf_nezisteni.parquet")
    spf = spf[spf.ku_kod == a.ku]
    mena = (spf.groupby("lv")["meno"]
               .agg(pocet_mien="size", mena=lambda s: " | ".join(s.head(5)) + (" …" if len(s) > 5 else ""))
               .reset_index())
    print(f"\nSPF: {spf.ku_nazov.iloc[0]} – {len(spf)} záznamov, {mena.lv.nunique()} LV")

    vysledky = []
    for reg in ("c", "e"):
        df, pole = parcely(reg, metas[reg], a.ku, a)
        if df is None or df.empty:
            continue
        if not pole["lv"]:
            print(f"   !! register {reg.upper()}: stĺpec s číslom LV sa nenašiel -> LV ZBGIS nevracia "
                  "(alebo zadaj --pole-lv podľa výpisu schémy)")
            continue
        t = pd.DataFrame({
            "register": reg.upper(),
            "lv": pd.to_numeric(df[pole["lv"]], errors="coerce").astype("Int64"),
            "parcela": df[pole["cislo"]] if pole["cislo"] else None,
            "vymera_m2": pd.to_numeric(df[pole["vymera"]], errors="coerce") if pole["vymera"] else None,
            "druh": df[pole["druh"]] if pole["druh"] else None,
        })
        vysledky.append(t)
    if not vysledky:
        print("\nZBGIS nevrátil číslo LV – spojenie so SPF nie je možné touto cestou.")
        return
    p = pd.concat(vysledky, ignore_index=True)
    p["druh_txt"] = p["druh"].map(lambda v: DRUHY.get(int(v), v) if str(v).isdigit() else v)
    p.to_csv(OUT / f"parcely_{a.ku}_spolu.csv", index=False)

    agg = (p.groupby(["lv", "register"])
             .agg(parciel=("parcela", "size"),
                  parcely=("parcela", lambda s: ", ".join(map(str, s.head(15))) + (" …" if len(s) > 15 else "")),
                  vymera_m2=("vymera_m2", "sum"),
                  druh=("druh_txt", lambda s: ", ".join(f"{k} ({v})" for k, v in s.value_counts().items())))
             .reset_index())
    spoj = mena.merge(agg, on="lv", how="left").sort_values("vymera_m2", ascending=False)
    spoj.to_csv(OUT / f"spoj_{a.ku}.csv", index=False)
    spoj.to_html(OUT / f"spoj_{a.ku}.html", index=False)
    napojene = spoj.parciel.notna().sum()
    print(f"\nSPF LV napojených na parcely ZBGIS: {napojene}/{len(mena)}")
    print(f"výmera spolu (napojené): {spoj.vymera_m2.sum() / 10000:.1f} ha")
    print(spoj.drop(columns=["mena"]).head(25).to_string(index=False))


if __name__ == "__main__":
    main()
