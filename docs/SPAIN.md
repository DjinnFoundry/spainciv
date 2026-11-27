# spainciv: Spain on the usaciv map

`uv run python -m pipeline all --country es` builds Spain into `sites/es/data/`; `uv run python -m pipeline serve
--country es` shows it. The US build is unchanged (`--country us` is the default). What makes a map one country or
the other is in `pipeline/countries/` (projection, hex size, levels, currency, output folders); Spain's sources are in
`pipeline/sources/es/`, its builder in `pipeline/build/spain.py`.

Decisions (and why) are in `DECISIONS.md`, what is missing in `ROADMAP.md`, what changed in `CHANGELOG.md`.

## Language

The Spanish site is in Spanish and English (DECISIONS A18–A21, E67). The language shown is the one in the URL
(`#lang=en`), else the one the visitor last picked (`localStorage`), else the first of the browser's languages the
site has, else Spanish; a small button at the end of the top bar switches (the page reloads in the other language) and
the shareable URL carries `lang=`, so a link opens in the sender's language (`web/js/app/country.js`,
`web/js/ext/lang/`). The US map has one language and no switch.

- **Interface**: `t(key)` in `web/js/i18n.js`. The Spanish table (`web/js/i18n/es/`) is written for Spain; the English
  one (`web/js/i18n/en/`) is usaciv's, about the United States; Spain in English reads `web/js/i18n/en-ES/` first,
  the keys whose English differs for Spain (provinces, municipalities, the Padrón, €), and falls back on `en`.
- **Numbers**: the language's locale (`Country.locales`): es-ES ("1,6 M", "35.000 €", "12,3 %", "1,5 B €" with B =
  billón) and en-IE for English ("1.6M", "€35,000", "12.3%", "€1.5T"). Numbers inside data texts are written by the
  pipeline in each language (`pipeline/core/lang.py`, `num`).
- **Data texts**: Spain's builders write every generated text as a `Text` in both languages (`tr(es, en)`). Each data
  file is written in Spanish, and `<name>.en.json` beside it holds only the English texts that differ, at the same
  path; the browser lays it over the file when the page is in English (`web/js/app/data.js`). Values are never
  repeated, so the overlays are small. A builder that rewrites another's file reads it with `load_web(...,
  texts=True)`. The tables shared with the US builders are translated in `pipeline/build/texts_es.py`; the Almanac's
  source entries take their English from the sources themselves (`pipeline/sources/es`).
- **Names**: a name taken from a source stays as the source writes it, in both languages (places, people, dishes,
  fiestas, denominations, museums, plants, mines); the map translates only the words it adds around it (E67).
- **Page**: the head, the social card and the credits are written in Spanish, the language of the data, because link
  previews never run the page; in English the page swaps its credits and description when it loads. The Unciv page is
  `jugar.html` in Spanish and `play.html` in English.

`tests/test_i18n.py` checks that every key and every data text exists in both languages, that no common English word
is left in the Spanish data and no Spanish one in the English view, and that the English for Spain does not speak of
the United States. A new interface string goes into `es`, `en` and, if its English is about the US, `en-ES`; a new
Spanish source gets its Almanac entry in `texts_es.SOURCES`; a new builder text is a `tr()`.

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
| `wikidata_es` | Wikidata SPARQL: World Heritage sites, cathedrals, museums, Bienes de Interés Cultural, castles (Q23413 and subclasses) and bullrings (Q1193438 and subclasses), without the demolished (P576) | CC0 | World Heritage and cathedral wonders; heritage, museums, castles and bullrings lenses (named in the tooltip) |
| `wikidata_personajes` | Wikidata SPARQL: people (Q5) whose place of birth (P19) has Spain, or a historical polity of the peninsula, as its country; their occupations (P106), positions (P39), Nobel Prizes (P166), canonization status (P411), sitelinks, dates (P569, P570) and birthplace coordinates (P625, or those of the place it is in, P131) | CC0 | Great people lenses (people per hex, main category per hex) and the people in the search box: 19 categories with a fame threshold each (DECISIONS E58–E59, F27) |
| `aena_airports` | AENA traffic 2025 (XLSX) + OurAirports positions (public domain) | Aena legal notice; OurAirports public domain | Airports |
| `puertos_estado` | Puertos del Estado: traffic 2025 by Port Authority (XLSX) + service areas (WFS, CC BY 4.0) | Puertos del Estado legal notice; WFS CC BY 4.0 | Ports |
| `siiu_universidades` | SIIU (Ministerio de Ciencia, Innovación y Universidades): students by centre 2024-25 and centre municipalities (XLSX) | Reuse citing the Ministry | Great-university wonders |
| `power_plants_es` | powerplantmatching (PyPSA, pinned commit) + OpenStreetMap power plants on the Canary Islands | CC BY 4.0; ODbL 1.0 | Power plants (resources) |
| `igme_minas` | IGME: Estadística Minera de España 2019 active workings (XLSX published with Panorama Minero 2022), placed at the matching deposit of IGME's BDMIN (ArcGIS REST) | IGME licence of use: free reuse citing the source (Ley 37/2007) | Mines (resources); for the Unciv map, every working by substance and municipality and BDMIN's large and medium deposits of coal, uranium, bauxite, iron, gold, copper and silver |
| `calidad_diferenciada` | eAmbrosia EU register (every Spanish name) + MAPA "Calidad diferenciada" areas (OGC API, 2017) + the areas of the names MAPA has not mapped, read from their EU single documents (EUR-Lex) and specifications into `data/calidad_diferenciada_zonas.csv` as communities, provinces, islands or municipalities | CC BY 4.0; specifications: official texts | Food & drink lens; Unciv resources |
| `pleiades_iberia` | Pleiades: peoples of ancient Iberia (points) and the regions named after peoples | CC BY 3.0 | Ancient peoples lens |
| `lenguas_es` | Navarre language zones (IDENA WFS) + Llei 4/1983 art. 36 (BOE API) | CC BY 4.0; legal text | Languages lens |
| `bandera_azul` | ADEAC Blue Flag 2026-27 list (PDF read into a CSV in the repo by `tools/bandera_azul_pdf.py`) | © ADEAC, cited | Blue Flag beaches lens |
| `gastronomia_es` | Spanish Wikipedia provincial cuisine categories, filtered to foods and drinks with Wikidata | CC BY-SA 4.0 (titles); CC0 | Regional dishes lens |
| `fiestas_interes_turistico` | Secretaría de Estado de Turismo: the Fiestas de Interés Turístico Internacional and Nacional pages of turismo.gob.es, placed in their municipalities by `pipeline/sources/es/data/fiestas_interes_turistico.csv` | Public-sector information, reuse citing the source (Ley 37/2007) | Fiestas lens (90 Internacional, 164 Nacional; a fiesta on both lists counts once, as Internacional), party index |
| `ine_viviendas_turisticas` | INE table 39363 (experimental statistic on tourist dwellings, latest period: May 2026) | CC BY 4.0, citing INE | Tourist dwellings per 1,000 inhabitants lens, party index |
| `osm_bares` | OpenStreetMap amenity=bar and amenity=pub (no cafés), one cached Overpass query, `out center` | ODbL 1.0 | Bars per 1,000 inhabitants lens (coverage uneven: cities and coasts far better mapped than villages), party index |
| `mivau_valor_tasado` | Ministerio de Vivienda, appraised value of free-market housing per m² (CSV VDP006_01), latest quarter with all 52 provinces | Public-sector information, citing the source | Home value lens, by province |
| `ine_padron` | INE table 29005 (Padrón revision by municipality) | CC BY 4.0, citing INE | Population, growth, density lens |
| `ine_pib` | INE table 80109 (Contabilidad Regional, GDP by province) | CC BY 4.0, citing INE | Gold (GDP) by province |
| `ine_censo_ocupados` | INE Annual Population Census, employed residents by CNAE section (tables 69962 and 69992) | CC BY 4.0, citing INE | Food, Production, Culture yields, jobs and employed of cities, provinces and Spain; the split of Science below the community |
| `ine_censo_divisiones` | INE Annual Population Census, employed residents by CNAE division (tables 69960 and 69980: Spain, provinces, 151 main cities) | CC BY 4.0, citing INE | Districts and city types |
| `ine_imasd` | INE R&D statistic (Estadística sobre actividades de I+D), all sectors: intramural R&D spending and R&D personnel (FTE) by autonomous community (table 82978; year from the national series, table 82944) | CC BY 4.0, citing INE | Science yield: R&D personnel, shared among a community's provinces and cities by their census J + M workers (DECISIONS F16) |
| `ine_adrh` | INE table 30824 (Atlas de Distribución de Renta de los Hogares) | CC BY 4.0, citing INE | Income lens (mean net income per person, 2024); household income of cities, provinces and Spain (mean net income per household: total income ÷ households, each municipality weighted by its households) |
| `ine_censo_actividad` | INE table 66594 (Annual Population Census, population 16+ by relationship with activity) | CC BY 4.0, citing INE | Unemployment: unemployed ÷ (employed + unemployed), summed over an area's municipalities (not the EPA rate, not SEPE registered unemployment) |
| `ine_adrh_indicadores` | INE ADRH tables 30832 (demographic indicators) and 30829 (relative income thresholds), read in a stream (about 1.5 GB with census sections) | CC BY 4.0, citing INE | Mean age lens (`age`, the mean: INE publishes no municipal median); poverty lens (`poverty`: residents below 60 % of the national median income per consumption unit, the EU at-risk-of-poverty threshold) |
| `ine_censo_nacimiento` | INE table 65031 (Annual Population Census, population by place of birth, Spain/abroad) | CC BY 4.0, citing INE | Born abroad lens (`foreign_born`): born abroad ÷ residents, by place of birth, not nationality |
| `ine_censo_formacion` | INE table 66592 (Annual Population Census, population 15+ by educational attainment, grouped) | CC BY 4.0, citing INE | Higher education lens (`bachelors`): 15+ with higher education (university and higher vocational) ÷ 15+; the 25+ universe of the US map exists only for municipalities of 500 residents or more |
| `ine_censo2021_indicadores` | INE 2021 Population and Housing Census, indicators by census section (`C2021_Indicadores.csv`) | CC BY 4.0, citing INE | Homeowners lens (`homeownership`): owned ÷ main dwellings, sections summed by municipality; the smallest municipalities (confidential sections) have no figure |
| `serpavi` | Ministerio de Vivienda, SERPAVI 2011-2024 (rents declared in IRPF, XLSX) | Public-sector information, reuse citing the source (Ley 37/2007) | Monthly rent: median rent of the whole dwelling, flats and houses and an area's municipalities combined as a lease-weighted mean of medians; rent ÷ income |
| `cobertura_banda_ancha` | Ministerio para la Transformación Digital: broadband coverage 2021-2025 by municipality (XLSX) | Public-sector information, reuse citing the source (Ley 37/2007) | Broadband lens: households covered at 100 Mbps or more under peak demand, June 2025 (coverage, not subscriptions) |
| `ine_censo_lugar_trabajo` | INE tables 69968 and 69987 (Annual Population Census, employed by place of work: Spain, provinces, 151 main cities) | CC BY 4.0, citing INE | Commuting lens: employed who work in another municipality ÷ employed with a known workplace; other municipalities take the rest of their province |
| `ine_esperanza_vida` | INE tables 1485 and 30687 (life expectancy at birth: provinces, 155 municipalities) | CC BY 4.0, citing INE | Life expectancy lens (2024); municipalities without their own figure take their province's |
| `ine_matrimonios` | INE tables 77172 and 37645 (MNP marriages by form of celebration: provinces, 150 main municipalities) | CC BY 4.0, citing INE | Religious weddings lens: religious ÷ all marriages (2025), by residence; other municipalities take the rest of their province |
| `effis_incendios` | EC JRC, EFFIS (Copernicus EMS) burnt-area perimeters 2016-2025, WFS | CC BY 4.0 | Wildfires lens: hectares burnt per hex, each fire's area shared among the hexes it covers |
| `ine_censo_agrario` | INE Censo Agrario 2020, tables 51175 (equine heads by agricultural comarca) and 75479 (each municipality's comarca) | CC BY 4.0, citing INE | Horses of the Unciv map: the comarcas with at least 4 times Spain's equines per km² |

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

## Unciv

Spain is also a map for [Unciv](https://github.com/yairm210/Unciv), the open-source Civilization V (desktop and
Android). `pipeline/build/spain_unciv.py` writes `sites/es/data/unciv.json`: the Unciv `TileMap` (83 × 53 tiles 25 km
across, base ruleset Civ V - Gods & Kings) and a summary of what is on it. `pipeline/build/unciv.py` holds the format
(read in Unciv's source, file paths in its docstring), the resampling of world.json's 10 km hexes, the terrain rules,
the rivers on tile edges and the resource placement that keeps every resource on a terrain the ruleset allows. When
the site is served or packaged, `pipeline/play.py` makes from it:

- `unciv/Spainciv-Unciv.zip`: the mod, one folder `Spainciv Unciv/` with `jsons/ModOptions.json`,
  `jsons/TileResources.json` (its own resource, the Iberian pig), `maps/España` (the map, gzip + base64 as Unciv saves
  it, naming the mod in `mapParameters.mods` so choosing it turns the mod on), `Images/ResourceIcons/Cerdo ibérico.png`
  with its atlas (`game.atlas`, `game.png`, `Atlases.json`, which Android needs), `preview.png`, a bilingual
  `README.md` and `LICENSE` (CC BY 4.0);
- `unciv/espana`: the bare map for the game without mods (the same map without the pig), saved as `España` by the
  page's link;
- `jugar.html` (Spanish) and `play.html` (English): how to play it and what is real data and what is game
  convention, linked from the help dialog in its language.

The page, the README and the resource names in Spanish and English are templates in `pipeline/templates/` (A17).
The rules and the reasons are DECISIONS.md E51–E57, E60–E62, A15, A17, F26, F28 and F29. The map was checked in Unciv 5.0.1 (the jar of the
GitHub release, run with `java -jar`): the mod installed through "Download mod from URL", the map in the editor with
every resource kept, and a 40-turn game with Spain in Madrid and seven AI civilizations on the other starting
locations (`docs/images/es-unciv-editor.jpg`, `docs/images/es-unciv-partida.jpg`).

The mod's GitHub repository (`DjinnFoundry/Spainciv-Unciv`, topics `unciv-mod` and `unciv-mod-maps`, so it shows in
the game's mod browser) holds the zip's folder as it is: unzip `unciv/Spainciv-Unciv.zip` from a fresh package and
commit the contents of `Spainciv Unciv/` at the repository's root.

The site is a Cloudflare Pages project of its own (`spainciv`, account Djinn Foundry), deployed by hand:

    uv run python -m pipeline package --country es
    wrangler pages deploy dist/spainciv --project-name spainciv --branch main
