"""Krok 2c: parcely C a E s výmerou a geometriou z otvorených dát ÚGKK (INSPIRE Cadastral Parcels)
+ príznak intravilán podľa hraníc zastavaného územia obce (ZUOB, GKÚ).

Zdroje (CC BY 4.0, ÚGKK SR / GKÚ Bratislava):
  https://opendata.skgeodesy.sk/static/INSPIRE/Cadastral_parcels/{Kraj}{C|E}.zip   (1 GML na k.ú.: {ku_kod}.gml)
  https://www.skgeodesy.sk/files/gku/produkty-sluzby/na-stiahnutie/zuob_gpkg.zip      (hranice ZUOB, EPSG:5514)
INSPIRE GML obsahuje: číslo parcely (cp:label), výmeru (cp:areaValue, m2), geometriu (EPSG:4258, poradie lat lon),
nationalCadastralReference "{ku}_{parcela}.{C|E}". NEOBSAHUJE číslo LV ani druh pozemku.

Spustenie:
    python scripts/06_inspire_parcely.py --tag nr_to --ku-csv data/kandidati_nr_to_ku.csv \
        --zip data/raw/inspire/NitrianskyC.zip data/raw/inspire/NitrianskyE.zip
Výstup: data/parcely_<tag>.parquet (1 riadok = 1 parcela), data/parcely_<tag>_ku.csv (súhrn k.ú.)
"""
import argparse
import sqlite3
import struct
import zipfile
from pathlib import Path

import pandas as pd
from lxml import etree
from pyproj import Transformer
from shapely import wkb as shp_wkb
from shapely.geometry import Polygon
from shapely.ops import polygonize, transform, unary_union
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]
NS = {"gml": "http://www.opengis.net/gml/3.2", "cp": "http://inspire.ec.europa.eu/schemas/cp/4.0"}
TAG_PARCEL = "{%s}CadastralParcel" % NS["cp"]
TO_JTSK = Transformer.from_crs("EPSG:4258", "EPSG:5514", always_xy=True).transform


def ring(poslist: str):
    v = list(map(float, poslist.split()))
    # INSPIRE/EPSG:4258 = lat lon; shapely chce (x=lon, y=lat)
    return [(v[i + 1], v[i]) for i in range(0, len(v), 2)]


def parcel_from_element(el):
    ref = el.findtext("cp:nationalCadastralReference", namespaces=NS) or ""
    label = el.findtext("cp:label", namespaces=NS) or ""
    area = el.findtext("cp:areaValue", namespaces=NS)
    polys = []
    for patch in el.iterfind(".//gml:PolygonPatch", namespaces=NS):
        ext = patch.find("gml:exterior/gml:LinearRing/gml:posList", namespaces=NS)
        if ext is None or not ext.text:
            continue
        ints = [ring(i.text) for i in patch.iterfind("gml:interior/gml:LinearRing/gml:posList", namespaces=NS) if i.text]
        try:
            polys.append(Polygon(ring(ext.text), ints))
        except Exception:  # noqa: BLE001
            pass
    geom = unary_union(polys) if polys else None
    ku, _, rest = ref.partition("_")
    reg = rest[-1] if rest.endswith((".C", ".E")) else ""
    return dict(ku_kod=int(ku) if ku.isdigit() else None, register=reg, parcela=label,
                vymera_m2=float(area) if area else None, geom=geom)


def parse_gml(data: bytes):
    out = []
    for _, el in etree.iterparse(__import__("io").BytesIO(data), events=("end",), tag=TAG_PARCEL):
        out.append(parcel_from_element(el))
        el.clear()
        while el.getprevious() is not None:
            del el.getparent()[0]
    return out


def gpkg_geom(blob: bytes):
    """GeoPackage binary -> shapely (hlavička: 'GP', ver, flags, srs_id, envelope)."""
    flags = blob[3]
    env_len = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[(flags >> 1) & 0x7]
    return shp_wkb.loads(blob[8 + env_len:])


def zuob_polygons(gpkg: Path):
    """Línie ZUOB (EPSG:5514) -> polygóny zastavaného územia podľa k.ú. (IDN5)."""
    c = sqlite3.connect(gpkg)
    by_ku = {}
    for idn5, blob in c.execute("select IDN5, Shape from zuob"):
        g = gpkg_geom(blob)
        lines = list(g.geoms) if g.geom_type == "MultiLineString" else [g]
        polys = list(polygonize(lines))
        if not polys:  # otvorená línia – skúsiť uzavrieť
            for ln in lines:
                cs = list(ln.coords)
                if len(cs) >= 3:
                    polys.append(Polygon(cs + [cs[0]]))
        if polys:
            by_ku.setdefault(int(idn5), []).extend(polys)
    return {k: unary_union(v).buffer(0) for k, v in by_ku.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--ku-csv", help="CSV so stĺpcom ku_kod (napr. data/kandidati_<tag>_ku.csv)")
    ap.add_argument("--ku", nargs="*", type=int)
    ap.add_argument("--zip", nargs="+", required=True)
    ap.add_argument("--zuob", default="data/raw/zuob/zuob.gpkg")
    a = ap.parse_args()

    kus = set(a.ku or [])
    if a.ku_csv:
        kus |= set(pd.read_csv(ROOT / a.ku_csv).ku_kod.astype(int))
    print(f"k.ú.: {len(kus)}")

    zu = zuob_polygons(ROOT / a.zuob)
    print(f"ZUOB polygóny pre {len(zu)} k.ú.; z našich k.ú. má ZUOB {len(kus & set(zu))}")

    rows = []
    for zp in a.zip:
        with zipfile.ZipFile(ROOT / zp) as z:
            names = {Path(n).stem: n for n in z.namelist() if n.lower().endswith(".gml")}
            hit = [k for k in kus if str(k) in names]
            print(f"{zp}: {len(names)} GML, z toho našich {len(hit)}")
            for k in sorted(hit):
                recs = parse_gml(z.read(names[str(k)]))
                zpoly = zu.get(k)
                for r in recs:
                    g = r.pop("geom")
                    if g is None or g.is_empty:
                        r.update(vymera_geom_m2=None, lon=None, lat=None, intravilan_podiel=None, wkb=None)
                    else:
                        gj = transform(TO_JTSK, g)
                        c = g.centroid
                        pod = (gj.intersection(zpoly).area / gj.area) if (zpoly is not None and gj.area > 0) else 0.0
                        r.update(vymera_geom_m2=round(gj.area, 1), lon=round(c.x, 7), lat=round(c.y, 7),
                                 intravilan_podiel=round(pod, 3), wkb=g.wkb)
                    rows.append(r)
                print(f"   {k}: {len(recs)} parciel", end="\r")
    df = pd.DataFrame(rows)
    df["intravilan"] = df.intravilan_podiel.fillna(0) >= 0.5
    df.to_parquet(ROOT / "data" / f"parcely_{a.tag}.parquet", index=False, compression="zstd")
    print(f"\nparciel spolu: {len(df)}  (C: {(df.register == 'C').sum()}, E: {(df.register == 'E').sum()})")

    s = (df.groupby(["ku_kod", "register"])
           .agg(parciel=("parcela", "size"), vymera_ha=("vymera_m2", lambda x: round(x.sum() / 1e4, 1)),
                intravilan_parciel=("intravilan", "sum"),
                intravilan_ha=("vymera_m2", lambda x: round(x[df.loc[x.index, "intravilan"]].sum() / 1e4, 1)))
           .reset_index())
    s.to_csv(ROOT / "data" / f"parcely_{a.tag}_ku.csv", index=False)
    print(s.head(20).to_string(index=False))


if __name__ == "__main__":
    main()
