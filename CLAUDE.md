# POZEMKY – pôda nezistených vlastníkov (SR)

Komunikácia s používateľom: po slovensky, stručne, prakticky. Výsledky ako tabuľka / stránka.
Pravidlá: len verejné zdroje určené na tento účel (SPF zoznam, ZBGIS služby, číselníky ÚGKK/GKÚ,
data.gov.sk). Nič neposielať tretím stranám. **Nesťahovať hromadne z katastrálneho portálu
(CICA/ESKN portal) – captcha a podmienky to zakazujú.**

Všetko je v `pozemky/`.

## Spúšťanie

```bash
cd pozemky
pip install -r requirements.txt
python scripts/01_spf_stiahni_spoj.py          # stiahne 7 CSV SPF a spojí -> data/spf_nezisteni.parquet
python scripts/01_spf_stiahni_spoj.py --bez-stahovania   # len spojenie z data/raw/*.csv
python scripts/02_ciselnik_ku.py               # číselník k.ú.->obec->okres->kraj + súhrny
python scripts/03_zbgis_overenie.py --ku 845337            # ZBGIS overenie 1 k.ú. (len zo SK pripojenia)
python scripts/03_zbgis_overenie.py --ku 845337 --len-schema  # len vypíše atribúty vrstiev
python scripts/04_kandidati.py --medzi Nitra Topoľčany --okresy Nitra Topoľčany --sirka 6000 --tag nr_to
                                               # kandidátne LV zo SPF pre koridor/okresy -> data/kandidati_<tag>.csv + web/kandidati_<tag>.json
python scripts/05_mena_struktura.py --vstup data/kandidati_nr_to.csv --tag nr_to --lv 840611:858
                                               # rozklad mien (priezvisko, rodné, manžel, nar., zom., č.d.) + rodinné klastre na LV
```

## Dáta (pozemky/data)

| súbor | obsah | v gite |
|---|---|---|
| `raw/` | 7 CSV SPF (~350 MB), gn_csv.zip, PDF ÚGKK | nie (.gitignore) |
| `spf_nezisteni.parquet` | spojený SPF zoznam: `ku_nazov, ku_kod, lv, meno, subor` | áno (~29 MB, zstd) |
| `ciselnik_ku.csv` | GNKU: `ku_kod, ku_nazov_gn, obec_kod, obec, okres_kod, okres, kraj_kod, kraj, x_jtsk, y_jtsk` | áno |
| `spf_ku_suhrn.csv` | počet záznamov a LV na k.ú. + obec/okres/kraj | áno |
| `spf_okres_suhrn.csv` | súhrn podľa okresov | áno |
| `zbgis/` | výstupy skriptu 03 (schémy, parcely, spoj) | nie |
| `kandidati_nr_to.csv` | LV v koridore Nitra–Topoľčany (56 k.ú.): `ku_kod, lv, pocet_nezist, s_udajom, s_umrtim, spf_pozn, mena, ku_nazov, obec, okres, os_dist` | áno |
| `kandidati_nr_to_ku.csv` | súhrn po k.ú. (LV, mien, LV s ≥2 / 3–8 / ≥9 menami) | áno |
| `mena_nr_to.csv` | 1 riadok = 1 osoba zo SPF zoznamu v koridore, štruktúrované polia (heuristika) | áno |
| `klastre_nr_to.csv` | rodinné klastre na LV (spojené cez kmeň priezviska / rodného priezviska, aj cez sobáš) | áno |

Stránky (pozemky/web, publikované ako artifacty):
- `krok1_prehlad.html` – súhrn SPF zoznamu: https://claude.ai/artifact/5K1SoTyaUq6e9Atp8wiKya
- `kandidati_nr_to.html` + `kandidati_nr_to.json` (načítava sa fetch-om ako supporting file) – LV Nitra–Topoľčany
  s menami a filtrami: https://claude.ai/artifact/GF1YrRzxjKBeewiXwiKyBf
  Pri republish treba JSON poslať v `files` s ABSOLÚTNOU cestou (cwd sa počas session mení).

Poznámky k menám v SPF exporte: poznámka sa opakuje (`Meno (pozn.) D:(pozn.)` alebo `Meno, (pozn.) pozn.`),
`ocisti_meno()` v skripte 04 ju odstráni. `č.d. 2310/20` = číslo denníka pozemkovej knihy (zápis/rok), NIE adresa.
`r.`/`rod.` = rodné priezvisko, `malol.`/`mal.` = maloletý v čase zápisu, `(SPF)` = poznámka o správe SPF.

## Zdroje

- SPF – Zoznam nezistených vlastníkov k 30.06.2026:
  https://pozfond.sk/verejny-pristup-k-informaciam/zoznam-nezistenych-vlastnikov/
  CSV: `https://pozfond.sk/wp-content/uploads/2026/07/{A_G,H_J,K_L,M_O,P_R,S_U,V_Z}-Nezisteni-vlastnici-k-30.06.2026.csv`
  (UTF-8 s BOM, `;`, CRLF; hlavička `KATASTRÁLNE ÚZEMIE;PORADOVÉ ČÍSLO;LV;MENO NEZNÁMEHO VLASTNÍKA`;
  „PORADOVÉ ČÍSLO“ = 6-miestny kód k.ú.)
- GKÚ – geografické názvy CSV (CC-BY 4.0, stav 21.07.2023), súbor `GNKU.csv` (cp1250, `;`):
  https://www.skgeodesy.sk/files/gku/produkty-sluzby/na-stiahnutie/gn_csv.zip
  IDN5/NM5 = k.ú., IDN4/NM4 = obec, IDN3/NM3 = okres, IDN2/NM2 = kraj, POINT_X/Y = S-JTSK (EPSG:5514).
- ÚGKK – zoznam k.ú. PDF (stav 9/2020) + zmeny názvov:
  https://www.skgeodesy.sk/sk/ugkk/geodezia-kartografia/standardizacia-geografickeho-nazvoslovia/nazvy-katastralnych-uzemi/
- ZBGIS/ESKN ArcGIS REST: `https://kataster.skgeodesy.sk/eskn/rest/services/VRM/parcels_{c,e}_view/MapServer/0`
  (pole `PARCEL_NUMBER` potvrdené z verejného kódu; ostatné polia NEOVERENÉ)
- INSPIRE OGC API Features: `https://inspirews.skgeodesy.sk/geoserver/cp/ogc/features/v1` (C),
  `.../cp_uo/ogc/features/v1` (E), kolekcia `CP.CadastralParcel` – podľa špecifikácie INSPIRE
  obsahuje číslo parcely, výmeru, geometriu; **LV ani druh pozemku nie**.

## Čo funguje

- Stiahnutie + spojenie SPF: 4 951 162 riadkov, 1 094 661 unikátnych (k.ú., LV), 3 520 k.ú.
  Pozor: ~6 800 riadkov má v mene `;` → CSV sa číta delením len prvých 3 bodkočiarok.
- Číselník GNKU: 3 559 k.ú., 79 okresov, 8 krajov; napojených 3 520/3 520 k.ú. zo SPF.

## Čo nefunguje / obmedzenia

- Z cloudového prostredia (Claude Code on the web) sú nedostupné: kataster.skgeodesy.sk,
  inspirews.skgeodesy.sk, zbgis.skgeodesy.sk, zbgisws.skgeodesy.sk, www.zbgis.sk, mpt.svp.sk
  (spojenie zhodené po TLS ~13 s; WebFetch → HTTP 503). www.skgeodesy.sk funguje.
  Pravdepodobne blokovanie zahraničných/dátacentrových IP → skript 03 spúšťať z notebooku (SK IP).
- SPF zoznam neobsahuje podiel ani celkový počet spoluvlastníkov na LV – len mená nezistených
  vlastníkov (počet mien na LV sa dá spočítať). Podiel je v časti B LV (len katastrálny portál).
- Overenie, či ESKN REST vracia číslo LV a druh pozemku: ČAKÁ na spustenie skriptu 03 zo SK IP.
