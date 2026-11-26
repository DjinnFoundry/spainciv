# spainciv: Spain on the usaciv map

`uv run python -m pipeline all --country es` builds Spain into `sites/es/data/`; `uv run python -m pipeline serve
--country es` shows it. The US build is unchanged (`--country us` is the default). What makes a map one country or
the other is in `pipeline/countries/` (projection, hex size, levels, currency, output folders); Spain's sources are in
`pipeline/sources/es/`, its builder in `pipeline/build/spain.py`.

Decisions (and why) are in `DECISIONS.md`, what is missing in `ROADMAP.md`, what changed in `CHANGELOG.md`.

## Language

The interface follows the country's `lang` (`es`): its strings are in `web/js/i18n/<lang>/*.js` (`t(key)` in
`web/js/i18n.js`, English as the fallback) and its numbers in `country.locale` (`web/js/format.js`: "1,6 M", "35.000 €",
"12,3 %"). Spain's builders write their texts in Spanish: the Spain-only catalogs where they are defined, and the tables
shared with the US builders (yield names, lens groups, land lenses, world.json tables, badge texts, the Almanac's source
entries and vintages) from `pipeline/build/texts_es.py`, so the US output stays in English and unchanged. A new string
in the interface goes into every language's table (`tests/test_i18n.py` checks it); a new Spanish source gets its
Almanac entry in `texts_es.SOURCES`.

## Sources

| Source id | Publisher | Licence | Used for |
|---|---|---|---|
| `siane` | IGN SIANE (Atlas Nacional de España) 1:3M, via rOpenSpain/mapSpain (pinned commit) | CC BY 4.0: Atlas Nacional de España (ANE), ign.es | Municipality and province outlines, municipal capitals (city positions) |
| `natural_earth_es` | Natural Earth 1:10m | Public domain | Neighbouring countries, lakes, rivers |
| `natural_earth_roads_es` | Natural Earth 1:10m roads and railroads | Public domain | Motorways, main roads and railroads on the map |
| `etopo_es` | NOAA NCEI ETOPO1 via ERDDAP | Public domain | Relief, sea depth |
| `corine` | Copernicus CLC 2018, read from the IGN/IDEE land-cover WMS by legend colour | CC BY 4.0 (IDEE); Copernicus free, full and open data policy | Land cover |
| `audes` | Ministerio de Vivienda y Agenda Urbana, Atlas Digital de las Áreas Urbanas: large urban areas 2025 and their municipalities | Public-sector information, reuse citing the source (Ley 37/2007) | Cities (urban areas) and their members |
| `oapn_parques` | OAPN (Red de Parques Nacionales), boundaries via its WFS | Public-sector information, reuse citing the source (Ley 37/2007) | National Park wonders, protected land |
| `wikidata_es` | Wikidata SPARQL: World Heritage sites, cathedrals, Bienes de Interés Cultural | CC0 | World Heritage and cathedral wonders |
| `aena_airports` | AENA traffic 2025 (XLSX) + OurAirports positions (public domain) | Aena legal notice; OurAirports public domain | Airports |
| `puertos_estado` | Puertos del Estado: traffic 2025 by Port Authority (XLSX) + service areas (WFS, CC BY 4.0) | Puertos del Estado legal notice; WFS CC BY 4.0 | Ports |
| `siiu_universidades` | SIIU (Ministerio de Ciencia, Innovación y Universidades): students by centre 2024-25 and centre municipalities (XLSX) | Reuse citing the Ministry | Great-university wonders |
| `power_plants_es` | powerplantmatching (PyPSA, pinned commit) + OpenStreetMap power plants on the Canary Islands | CC BY 4.0; ODbL 1.0 | Power plants (resources) |
| `igme_minas` | IGME: Estadística Minera de España 2019 active workings (XLSX published with Panorama Minero 2022), placed at the matching deposit of IGME's BDMIN (ArcGIS REST) | IGME licence of use: free reuse citing the source (Ley 37/2007) | Mines (resources) |
| `calidad_diferenciada` | MAPA "Calidad diferenciada" areas (OGC API, 2017) + eAmbrosia EU register | CC BY 4.0 | Food & drink lens |
| `pleiades_iberia` | Pleiades: peoples of ancient Iberia (points) and the regions named after peoples | CC BY 3.0 | Ancient peoples lens |
| `lenguas_es` | Navarre language zones (IDENA WFS) + Llei 4/1983 art. 36 (BOE API) | CC BY 4.0; legal text | Languages lens |
| `bandera_azul` | ADEAC Blue Flag 2026-27 list (PDF read into a CSV in the repo by `tools/bandera_azul_pdf.py`) | © ADEAC, cited | Blue Flag beaches lens |
| `gastronomia_es` | Spanish Wikipedia provincial cuisine categories, filtered to foods and drinks with Wikidata | CC BY-SA 4.0 (titles); CC0 | Regional dishes lens |
| `ine_padron` | INE table 29005 (Padrón revision by municipality) | CC BY 4.0, citing INE | Population, growth, density lens |
| `ine_pib` | INE table 80109 (Contabilidad Regional, GDP by province) | CC BY 4.0, citing INE | Gold (GDP) by province |
| `ine_censo_ocupados` | INE Annual Population Census, employed residents by CNAE section (tables 69962 and 69992) | CC BY 4.0, citing INE | Food, Production, Culture yields, jobs and employed of cities, provinces and Spain; the split of Science below the community |
| `ine_censo_divisiones` | INE Annual Population Census, employed residents by CNAE division (tables 69960 and 69980: Spain, provinces, 151 main cities) | CC BY 4.0, citing INE | Districts and city types |
| `ine_imasd` | INE R&D statistic (Estadística sobre actividades de I+D), all sectors: intramural R&D spending and R&D personnel (FTE) by autonomous community (table 82978; year from the national series, table 82944) | CC BY 4.0, citing INE | Science yield: R&D personnel, shared among a community's provinces and cities by their census J + M workers (DECISIONS F16) |
| `ine_adrh` | INE table 30824 (Atlas de Distribución de Renta de los Hogares) | CC BY 4.0, citing INE | Income lens (mean net income per person, 2024); household income of cities, provinces and Spain (mean net income per household: total income ÷ households, each municipality weighted by its households) |
| `ine_censo_actividad` | INE table 66594 (Annual Population Census, population 16+ by relationship with activity) | CC BY 4.0, citing INE | Unemployment: unemployed ÷ (employed + unemployed), summed over an area's municipalities (not the EPA rate, not SEPE registered unemployment) |
| `serpavi` | Ministerio de Vivienda, SERPAVI 2011-2024 (rents declared in IRPF, XLSX) | Public-sector information, reuse citing the source (Ley 37/2007) | Monthly rent: median rent of the whole dwelling, flats and houses and an area's municipalities combined as a lease-weighted mean of medians; rent ÷ income |

Each source's exact files, URLs and checksums are in `sources.json` (the Almanac).

## Publishing

`uv run python -m pipeline package --country es` writes `spainciv.zip` and `dist/spainciv/`, the static site for
<https://spainciv.djinnfoundry.com/> (`site_url` in `pipeline/countries/es.py`). `web/index.html` is written for the
United States; `pipeline/site.py` gives Spain's page, when it is packaged or served, the head from the country's
`page` (Spanish title and description, canonical, og:* and twitter:* pointing at `site_url`) and a credit line along
the bottom of the map: the data sources, the SIANE attribution its CC BY 4.0 licence asks for, and usaciv's credit.
The same values reach the browser in `<script id="country-page">`, so the share image prints the right address,
sources and notice without rebuilding `world.json`. The social card, `og-image.png` (1200×630), is drawn from
`world.json`, `cities.json` and the country's `page` by `pipeline/card.py` whenever the site is packaged or served,
so it follows the data; it is not kept in the repo.

The site is a Cloudflare Pages project of its own (`spainciv`, account Djinn Foundry), deployed by hand:

    uv run python -m pipeline package --country es
    wrangler pages deploy dist/spainciv --project-name spainciv --branch main
