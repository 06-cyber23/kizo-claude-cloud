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
python scripts/06_inspire_parcely.py --tag nr_to --ku-csv data/kandidati_nr_to_ku.csv \
    --zip data/raw/inspire/NitrianskyC.zip data/raw/inspire/NitrianskyE.zip
                                               # parcely C+E s výmerou, geometriou a príznakom intravilán (ZUOB) -> data/parcely_<tag>.parquet
```
Zipy parciel: `curl -o data/raw/inspire/NitrianskyC.zip https://opendata.skgeodesy.sk/static/INSPIRE/Cadastral_parcels/NitrianskyC.zip`
(C 294 MB, E 220 MB; celé SR SlovenskoC.zip 2,28 GB / SlovenskoE.zip 1,71 GB). ZUOB: `data/raw/zuob_gpkg.zip` z
https://www.skgeodesy.sk/files/gku/produkty-sluzby/na-stiahnutie/zuob_gpkg.zip. GeoJSON pre web (web/parcely/*.geojson, 96 MB)
sa generuje z parquetu ad hoc (kód v histórii session; nie je v gite – pozri web/parcely/index.csv).

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
| `parcely_nr_to.parquet` | 258 571 parciel (C 181 266, E 77 305) v 56 k.ú.: `ku_kod, register, parcela, vymera_m2 (úradná), vymera_geom_m2, lon, lat, intravilan_podiel, intravilan, wkb (EPSG:4258)` | áno (35 MB) |
| `parcely_nr_to_ku.csv` | súhrn parciel po k.ú. a registri (počet, ha, v zastavanom území) | áno |

Stránky (pozemky/web, publikované ako artifacty):
- `krok1_prehlad.html` – súhrn SPF zoznamu: https://claude.ai/artifact/5K1SoTyaUq6e9Atp8wiKya
- `kandidati_nr_to.html` + `kandidati_nr_to.json` (načítava sa fetch-om ako supporting file) – LV Nitra–Topoľčany
  s menami a filtrami: https://claude.ai/artifact/GF1YrRzxjKBeewiXwiKyBf
  Pri republish treba JSON poslať v `files` s ABSOLÚTNOU cestou (cwd sa počas session mení).
- `parcely_mapa.html` + `parcely/{ku}_{C|E}.geojson` (112 súborov, 96 MB, publikované v 2 dávkach ≤ 60 MB) – vlož čísla
  parciel z LV → výmera, zastavané územie, mapa (Leaflet z cdnjs, bez podkladových dlaždíc – CSP artifactu):
  https://claude.ai/artifact/Ghi4tP5spaMfMQ1vjgetWc
- `velke_parcely.html` + `velke_parcely.json` (3 MB) – OTOČENÝ POSTUP: najväčšie parcely E (≥ 1 ha) a parcely ≥ 600 m²
  v zastavanom území (E aj C) po k.ú., odkaz do ZBGIS; človek zadá číslo LV z mapy → stránka ho porovná so SPF
  zoznamom (všetkých 18 175 LV koridoru s menami). Zadané LV sa pamätajú v localStorage.
  https://claude.ai/artifact/XG4jDCkb2J65m4yU4bZSWB
  Test LV 858 Nitrianska Streda (ručne na portáli): E 180/1 (1 144 m²) + 371 (2 780 m²), orná pôda, mimo ZÚ,
  6 podielov (4/12, 4/12, 4×1/12), správa SPF → sedí s otvorenými dátami na m², ale nerentabilné.

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
  obsahuje číslo parcely, výmeru, geometriu; **LV ani druh pozemku nie**. Hostiteľ odtiaľto blokovaný.
- **INSPIRE HVD hromadné súbory (FUNGUJE odtiaľto):** https://opendata.skgeodesy.sk/static/INSPIRE/Cadastral_parcels/{Kraj}{C|E}.zip,
  CC BY 4.0, aktualizácia štvrťročne (stav dát 30.09.2026), 1 GML na k.ú. (`{ku_kod}.gml`, INSPIRE CP 4.0, EPSG:4258,
  posList = lat lon). Atribúty: cp:label (číslo parcely), cp:areaValue (úradná výmera m2), geometria,
  nationalCadastralReference `{ku}_{parcela}.{C|E}`. Metadáta: rpi.gov.sk (API /api/collection_record/{id}),
  C = 1d9ceaef-b3c6-4441-96df-a3ec353c7451, E = 36b39dd7-001a-4734-a98e-ee01aa9f7a96. V registri E sa to isté číslo
  parcely môže v k.ú. vyskytnúť 2× (530 prípadov v koridore) – rozlíšiť polohou.
- GKÚ ZUOB – hranice zastavaného územia obce k 1.1.1990 (zákon 220/2004), GPKG EPSG:5514, línie po k.ú. (IDN5) →
  polygonize. Použité ako náhrada „intravilán“ (parcela = v zastavanom území, ak ≥ 50 % výmery leží vnútri).
- ESKN REST polia (z verejného kódu, workflow 1): PARCEL_NUMBER, CADASTRAL_UNIT_ID (interné id k.ú., nie kód),
  DESCRIPTIVE_AREA_OF_PARCEL, FOLIO_ID (interné id LV – NIE číslo LV), NATURE_OF_LAND_USE_ID (kód druhu 1–10).
  `where=` blokuje WAF, funguje objectIds / priestorový dopyt; geoblok zahraničných IP. Číslo LV anonymne nedostupné;
  LV/vlastníci len cez ESKN portál s prihlásením (od 1.7.2026; neoverené).

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
- Overenie, či ESKN REST vracia číslo LV a druh pozemku: ČAKÁ na spustenie skriptu 03 zo SK IP (podľa verejného kódu
  vracia len FOLIO_ID = interné id, takže väzba k.ú.+LV → parcely pravdepodobne anonymne nejde).
- Druh pozemku: v otvorených dátach nie je. Náhrady: zastavané územie (ZUOB), prípadne LPIS / krajinná pokrývka.
- Captcha katastrálneho portálu sa NEOBCHÁDZA ani so súhlasom používateľa (prístupová kontrola, podmienky portálu).
- GitHub Actions ako „iná IP“ na overenie ESKN REST: zablokované bezpečnostným klasifikátorom (obchádzanie sieťového
  obmedzenia) – nepoužívať. Pracovný postup: človek ručne prečíta čísla parciel z LV (1 LV = 1 nahliadnutie na portál)
  a vloží ich do parcely_mapa.html.
