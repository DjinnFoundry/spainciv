# spainciv: Spain on the usaciv map

`uv run python -m pipeline all --country es` builds Spain into `sites/es/data/`; `uv run python -m pipeline serve
--country es` shows it. The US build is unchanged (`--country us` is the default). What makes a map one country or
the other is in `pipeline/countries/` (projection, hex size, levels, currency, output folders); Spain's sources are in
`pipeline/sources/es/`, its builder in `pipeline/build/spain.py`.

Decisions (and why) are in `DECISIONS.md`, what is missing in `ROADMAP.md`, what changed in `CHANGELOG.md`.

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
| `ine_padron` | INE table 29005 (Padrón revision by municipality) | CC BY 4.0, citing INE | Population, growth, density lens |
| `ine_pib` | INE table 80109 (Contabilidad Regional, GDP by province) | CC BY 4.0, citing INE | Gold (GDP) by province |
| `ine_censo_ocupados` | INE Annual Population Census, employed residents by CNAE section (tables 69962 and 69992) | CC BY 4.0, citing INE | Food, Production, Science, Culture yields, jobs and employed of cities, provinces and Spain |
| `ine_censo_divisiones` | INE Annual Population Census, employed residents by CNAE division (tables 69960 and 69980: Spain, provinces, 151 main cities) | CC BY 4.0, citing INE | Districts and city types |
| `ine_adrh` | INE table 30824 (Atlas de Distribución de Renta de los Hogares) | CC BY 4.0, citing INE | Income lens (mean net income per person, 2024) |

Each source's exact files, URLs and checksums are in `sources.json` (the Almanac).

## Publishing

`uv run python -m pipeline package --country es` writes `spainciv.zip` and `dist/spainciv/`, the static site for
<https://spainciv.djinnfoundry.com/> (`site_url` in `pipeline/countries/es.py`). `web/index.html` is written for the
United States; `pipeline/site.py` gives Spain's page, when it is packaged or served, the head from the country's
`page` (Spanish title and description, canonical, og:* and twitter:* pointing at `site_url`) and a credit line along
the bottom of the map: the data sources, the SIANE attribution its CC BY 4.0 licence asks for, and usaciv's credit.
The same values reach the browser in `<script id="country-page">`, so the share image prints the right address,
sources and notice without rebuilding `world.json`. The social card is `sites/es/og-image.png` (1200×630, made from
the map's own share image); files in `sites/es/` other than `data/` replace web/'s files of the same name.

The site is a Cloudflare Pages project of its own (`spainciv`, account Djinn Foundry), deployed by hand:

    uv run python -m pipeline package --country es
    wrangler pages deploy dist/spainciv --project-name spainciv --branch main
