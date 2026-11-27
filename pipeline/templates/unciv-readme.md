# Spainciv Unciv

[Español](#español) · [English](#english)

![El mapa / The map](preview.png)

## Español

España como mapa de [Unciv](https://github.com/yairm210/Unciv), la versión libre de Civilization V, sacado del mapa
de [$product]($url): costa, relieve, ríos, cubierta del suelo y recursos de datos abiertos.

- $width × $height casillas de $tile_km km ($land_tiles de tierra, $national_land_tiles de ellas españolas).
- Reglas: Civ V - Gods & Kings, las de serie, más las $n_nations comunidades autónomas como civilizaciones, Ceuta y
  Melilla como ciudades-estado, un recurso propio, el cerdo ibérico, y el suceso de la temporada de incendios. Probado
  en Unciv $release.
- Cada comunidad empieza en su capital, con su bandera, sus municipios más poblados (Padrón $padron_year) como
  nombres de ciudad y una ventaja sobre el recurso que más tiene. Elige la tuya en la bandera de tu jugador.
- Al elegir el mapa «$map_name» en una partida nueva, Unciv activa este mod por sí solo.

| Civilización | Empieza en | Ventaja | Tendencia de inicio |
|---|---|---|---|
$nations_es

| Recurso | Casillas | De dónde sale |
|---|---|---|
$rows_es

### Temporada de incendios

Cada $fire_check_es turnos, cada civilización mayor puede sufrir un gran incendio en su territorio. Puede enviar
brigadas (oro: $fire_cost_1_es, $fire_cost_2_es o $fire_cost_3_es según la era, por la velocidad de la partida) o dejar
que se apague solo (-$fire_penalty_es % de producción en todas sus ciudades durante $fire_penalty_turns_es turnos).
Dato: los $fire_n_es incendios de $fire_ha_es ha o más que el EFFIS (Copernicus, CC BY 4.0) cartografió en España de
$fire_from_es a $fire_to_es, repartidos entre las casillas que cubrió cada uno. Convención: un turno es una temporada,
el incendio de cada temporada cae en tu territorio con la parte de España que tienes (la suma de los pesos de tus
casillas entre $fire_unit_es; toda España, uno por temporada, frente a unos $fire_per_season_es en el EFFIS), se comprueba cada $fire_check_es turnos y el precio y el castigo son del juego.

| Casilla | Casillas españolas | Grandes incendios por casilla y temporada | Peso |
|---|---|---|---|
$fire_rows_es

Cómo instalarlo y qué es dato real y qué es convención del juego: $url/$page

## English

Spain as a map for [Unciv](https://github.com/yairm210/Unciv), the open-source Civilization V, built from the
[$product]($url) map: coast, relief, rivers, land cover and resources from open data.

- $width × $height tiles $tile_km km across ($land_tiles land tiles, $national_land_tiles of them Spanish).
- Ruleset: Civ V - Gods & Kings, the default, plus Spain's $n_nations autonomous communities as civilizations, Ceuta
  and Melilla as city-states, one resource of its own, the Iberian pig («Cerdo ibérico»), and the fire season event.
  Tested in Unciv $release.
- Each community starts in its capital, with its flag, its most populous municipalities ($padron_year Padrón) as city
  names and an advantage on the resource it holds most of. Pick yours on your player's flag.
- When you pick the map «$map_name» for a new game, Unciv turns this mod on by itself.

| Civilization | Starts in | Advantage | Start bias |
|---|---|---|---|
$nations_en

| Resource | Tiles | Source |
|---|---|---|
$rows_en

### Fire season

Every $fire_check_en turns, each major civilization may get a great fire on its land. It can send fire brigades (gold:
$fire_cost_1_en, $fire_cost_2_en or $fire_cost_3_en by era, times the game speed) or let it burn out
(-$fire_penalty_en% Production in all its cities for $fire_penalty_turns_en turns). Data: the $fire_n_en fires of
$fire_ha_en ha or more that EFFIS (Copernicus, CC BY 4.0) mapped in Spain from $fire_from_en to $fire_to_en, each
shared among the tiles it covered. Convention: a turn is one season, each season's fire lands on your territory with
the share of Spain you own (the sum of your tiles' weights over $fire_unit_en; all of Spain, one a season, against
about $fire_per_season_en in EFFIS), the check runs every $fire_check_en
turns, and the price and the penalty are the game's.

| Tile | Spanish tiles | Great fires per tile per season | Weight |
|---|---|---|---|
$fire_rows_en

How to install it, and what is real data and what is game convention: $url/$page_en

Licence: CC BY 4.0 (see LICENSE).
