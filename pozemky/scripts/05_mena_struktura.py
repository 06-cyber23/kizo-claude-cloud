"""Krok 2b: rozklad mien zo SPF zoznamu na štruktúrované polia + rodinné klastre na LV.

Heuristika nad textom exportu SPF (formát nie je jednotný, presnosť nie je 100 %).
Polia: priezvisko, meno, rodne (rodné priezvisko), manzel (meno manžela/ky), manzel_rodne,
       nar, zom, cd (čísla denníka pozemkovej knihy "č.d. 2478/32" = zápis 2478 z r. 1932),
       malol (maloletý pri zápise), adresa, spf (poznámka SPF).
Klastre: osoby na jednom LV spojené cez zhodné priezvisko alebo rodné priezvisko
         (= pravdepodobne jedna rodina / súrodenci) – východisko pre genealóga.

Spustenie:
    python scripts/05_mena_struktura.py --vstup data/kandidati_nr_to.csv --tag nr_to
    python scripts/05_mena_struktura.py --vstup data/kandidati_nr_to.csv --tag nr_to --lv 840611:858 863548:4577
Výstup: data/mena_<tag>.csv (1 riadok = 1 osoba), data/klastre_<tag>.csv (1 riadok = 1 klaster na LV)
"""
import argparse
import re
import unicodedata
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

R_NAR = re.compile(r"nar\.?\s*([0-9]{1,2}\.\s?[0-9]{1,2}\.\s?[0-9]{4}|[0-9]{4})")
R_ZOM = re.compile(r"(?:zomr?\.|zomrel[a]?|Dátum úmrtia:?|úmrt\w*:?)\s*([0-9]{1,2}\.\s?[0-9]{1,2}\.\s?[0-9]{4}|[0-9]{4})", re.I)
R_CD = re.compile(r"č\.?\s?d\.?\s?(\d{1,5}/\d{2,4})")
R_RODNE = re.compile(r"\br(?:od)?\.\s?([A-ZÁ-Ž][\w\-]+)")
R_MANZ = re.compile(r"(?:manž\.?|manžel(?:ka)?|man\.|\bm\.|\bž\.)\s?([A-ZÁ-Ž][\w\-]+)(?:\s+r(?:od)?\.\s?([A-ZÁ-Ž][\w\-]+))?")
R_MALOL = re.compile(r"malol|\bmal\.", re.I)
R_ADRESA = re.compile(r"adresa:?\s*([^()]+?)(?:\)|$)", re.I)
R_SPF = re.compile(r"\bSPF\b")
R_HLAVA = re.compile(r"^\s*([A-ZÁ-Ža-zá-ž][\w\-']+)\s+([A-ZÁ-Ža-zá-ž][\w\-']+)")


def bez_diakritiky(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()


def kmen(priezvisko: str) -> str:
    """Zjednotí mužský/ženský tvar: Remeňová -> remen, Kunovská -> kunovsk, Lojka -> lojka."""
    k = bez_diakritiky(priezvisko)
    for suf in ("ova", "sky", "ska", "cky", "cka", "a"):
        if k.endswith(suf) and len(k) - len(suf) >= 3:
            return k[: -len(suf)]
    return k


def rozlož(meno: str) -> dict:
    s = re.sub(r"\s+", " ", meno).strip()
    hl = s.split(",")[0]
    m = R_HLAVA.match(hl)
    priezvisko, krstne = (m.group(1), m.group(2)) if m else (hl.split(" ")[0], "")
    rodne = R_RODNE.search(s)
    # 'r. X' hneď za menom patrí osobe; 'manž. Anna rod. Y' patrí manželke
    manz = R_MANZ.search(s)
    spany = [(x.start(), x.end()) for x in R_MANZ.finditer(s)]
    rodne_os = None
    for mm in R_RODNE.finditer(s):
        if not any(a <= mm.start() <= b for a, b in spany):
            rodne_os = mm.group(1)
            break
    nar, zom = R_NAR.search(s), R_ZOM.search(s)
    adr = R_ADRESA.search(s)
    return {
        "priezvisko": priezvisko, "meno": krstne,
        "rodne": rodne_os or "",
        "manzel": manz.group(1) if manz else "", "manzel_rodne": (manz.group(2) or "") if manz else "",
        "nar": nar.group(1).replace(" ", "") if nar else "",
        "zom": zom.group(1).replace(" ", "") if zom else "",
        "cd": ";".join(dict.fromkeys(R_CD.findall(s))),
        "malol": bool(R_MALOL.search(s)),
        "adresa": adr.group(1).strip(" ,") if adr else "",
        "spf": bool(R_SPF.search(s)),
    }


def klastre(osoby: pd.DataFrame) -> list[dict]:
    """Spojí osoby na LV cez zhodný kmeň priezviska alebo rodného priezviska (union-find)."""
    n = len(osoby)
    rodic = list(range(n))

    def najdi(i):
        while rodic[i] != i:
            rodic[i] = rodic[rodic[i]]
            i = rodic[i]
        return i

    kluce = []
    for r in osoby.itertuples():
        k = {kmen(r.priezvisko)}
        if r.rodne:
            k.add(kmen(r.rodne))
        kluce.append(k)
    for i in range(n):
        for j in range(i + 1, n):
            if kluce[i] & kluce[j]:
                rodic[najdi(i)] = najdi(j)
    sk = {}
    for i in range(n):
        sk.setdefault(najdi(i), []).append(i)
    vysl = []
    for idx in sk.values():
        cast = osoby.iloc[idx]
        rody = sorted({cast.rodne[cast.rodne != ""].mode().iloc[0]} if (cast.rodne != "").any() else set())
        vysl.append({
            "osob": len(idx),
            "rod": rody[0] if rody else cast.priezvisko.mode().iloc[0],
            "priezviska": ", ".join(sorted(set(cast.priezvisko))),
            "osoby": " | ".join(f"{p.priezvisko} {p.meno}" + (f" r. {p.rodne}" if p.rodne and kmen(p.rodne) != kmen(p.priezvisko) else "")
                                 for p in cast.itertuples()),
            "roky": ", ".join(sorted({x for x in list(cast.nar) + list(cast.zom) if x})),
            "cd": ", ".join(sorted({c for cc in cast.cd for c in cc.split(";") if c})),
        })
    return sorted(vysl, key=lambda d: -d["osob"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vstup", default="data/kandidati_nr_to.csv")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--lv", nargs="*", help="ukázať klastre pre ku_kod:lv")
    a = ap.parse_args()

    lv = pd.read_csv(ROOT / a.vstup)
    rows = []
    for r in lv.itertuples():
        for m in str(r.mena).split(" | "):
            d = rozlož(m)
            d.update(ku_kod=r.ku_kod, ku_nazov=r.ku_nazov, lv=r.lv, meno_povodne=m)
            rows.append(d)
    os_ = pd.DataFrame(rows)
    os_.to_csv(ROOT / "data" / f"mena_{a.tag}.csv", index=False)
    print(f"osôb: {len(os_)}; s rodným priezviskom: {(os_.rodne != '').mean():.0%}; s manželom: {(os_.manzel != '').mean():.0%}; "
          f"s nar.: {(os_.nar != '').mean():.0%}; so zom.: {(os_.zom != '').mean():.0%}; s č.d.: {(os_.cd != '').mean():.0%}; "
          f"s adresou: {(os_.adresa != '').mean():.0%}")

    kl = []
    for (ku, l), g in os_.groupby(["ku_kod", "lv"]):
        for c in klastre(g.reset_index(drop=True)):
            c.update(ku_kod=ku, ku_nazov=g.ku_nazov.iloc[0], lv=l, osob_na_lv=len(g))
            kl.append(c)
    kl = pd.DataFrame(kl)
    kl.to_csv(ROOT / "data" / f"klastre_{a.tag}.csv", index=False)
    print(f"klastrov: {len(kl)}; LV s 1 rodinou: {(kl.groupby(['ku_kod','lv']).size() == 1).sum()}")

    if a.lv:
        for p in a.lv:
            ku, l = map(int, p.split(":"))
            g = kl[(kl.ku_kod == ku) & (kl.lv == l)]
            if g.empty:
                print(f"\n== {ku}:{l} – nenájdené vo vstupe")
                continue
            print(f"\n== {g.ku_nazov.iloc[0]} LV {l} – {g.osob_na_lv.iloc[0]} osôb, {len(g)} rodín")
            for c in g.itertuples():
                print(f"   rod {c.rod} ({c.osob}): {c.osoby}" + (f"  [roky: {c.roky}]" if c.roky else "") + (f"  [č.d.: {c.cd}]" if c.cd else ""))


if __name__ == "__main__":
    main()
