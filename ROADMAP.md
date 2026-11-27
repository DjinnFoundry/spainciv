# Roadmap

Lo que falta para spainciv, por orden de valor. Al terminar algo se borra de aquí y se apunta en `CHANGELOG.md`; las
decisiones que salgan van a `DECISIONS.md`.

## Ahora

1. **Revisión de David** de las decisiones marcadas «Claude» en `DECISIONS.md`.

## Huecos conocidos

- Lentes diarias (E33–E38): trabajan fuera, esperanza de vida y bodas solo tienen dato propio en unos 150 municipios;
  los demás llevan el resto de su provincia (o la provincia, en la esperanza de vida). Incendios: faltan los
  menores de unas 30 ha que no ve el EFFIS, y no hay lente de inundaciones (sin conjunto oficial abierto por municipio).
  La banda ancha es cobertura, no contratación.
- Minas: la lista por mina más reciente del IGME es la de 2019; La Parrilla (wolframio, desde 2020) y Alquife (hierro,
  2021) no salen. Cuatro de las 25 están en el centro de su municipio (sin yacimiento del BDMIN que case).
- Cada fuente nueva de España necesita su ficha en `texts_es.SOURCES`, o sale en inglés en el Almanaque.
- Lentes de fauna (E90, F37): son las cuadrículas de 2013-2018. España mandó a la UE las de 2019-2024 en julio de 2025,
  pero el MITECO aún no las publica (comprobado el 2026-11-27). Cuando salgan, cambiar las URL y el periodo de
  `especies.py`: los códigos de cuadrícula son los mismos. Se ve la falta en el lobo (552 cuadrículas en el mapa, 1.357
  estables en el censo 2021-2024) y en el lince, que ya está en Murcia, Castilla y León y Madrid.
- El oro de las ciudades queda vacío: no hay PIB municipal oficial, y la renta o las bases del IRPF no lo sustituyen (E31).
- Valor de la vivienda: la lente es provincial (E49); el valor tasado municipal (más de 25.000 habitantes) solo está en un XLS binario de un servidor que responde 503. Si vuelve, la lente puede bajar a municipio.
- Lentes de personas: la edad es la media (no hay mediana municipal), los estudios superiores cuentan desde los 15 años (E41) y la vivienda en propiedad es del Censo de 2021, sin los 1.357 municipios de secciones confidenciales (E43).
- La renta de los hogares es una media (el INE no publica la mediana municipal) y el alquiler de un área es la media de medianas municipales ponderada por contratos (E27, E29).
- Los campos de los consejeros apuntan a los ids de fuente de EE UU (`acs_1yr`, `bea_gdp`) también en España.
- Los ciudadanos de la City View, el comercio y los desastres siguen siendo solo de EE UU.
- Ejército (E67-E71): faltan los efectivos por provincia del Anuario Estadístico Militar (ODS de 2023 en datos.gob.es;
  `publicaciones.defensa.gob.es` no respondía el 27-11-2026) y el gasto de Defensa por provincia. Los límites son los
  de OpenStreetMap, y 165 de las 478 instalaciones no tienen rama (oficinas, residencias, institutos del Órgano
  Central y sitios cuyo nombre no la dice).
- Distritos: describen el municipio núcleo de cada área (5 de las 86 áreas tienen un núcleo sin divisiones CNAE en el
  Censo y se quedan sin distritos); los municipios no tienen distritos propios. Sin Encampment (defensa no se separa a
  dos dígitos).
- Empleo de las áreas: sin los miembros de menos de 500 habitantes (tres áreas, unos 6.500 residentes).
- El Padrón 2025 tiene 8.138 municipios y el SIANE 2026 8.132.
- 298 hexágonos de mar, sobre todo alrededor del recuadro de Canarias, no tienen muestras de ETOPO (bajo el recuadro se descartan a propósito).
- En la vista inicial, el minimapa tapa parte del recuadro de Canarias.
- Platos regionales: llegan a la provincia, no a la comarca; no hay fuente más fina. La cobertura de la Wikipedia es
  desigual (Madrid 47, Álava 1).
- Lenguas: falta el aragonés y el catalán de Aragón (sin lista publicada de municipios) y los dialectos (sin
  delimitación oficial).
- Bandera Azul: cada playa va a la costa de su municipio, no a su posición; se podría afinar con las playas de Wikidata.
- Bares: OpenStreetMap no es un censo (42.122 bares y pubs); en los pueblos poco mapeados un cero puede ser un bar sin
  mapear, y en los muy pequeños un solo bar dispara la tasa por habitante.
- Fiestas: la colocación es a mano (CSV); una declaración nueva en turismo.gob.es hace fallar el build hasta situarla.
  Faltan las fiestas de interés turístico autonómicas.
- Pernoctaciones hoteleras por punto turístico (EOH del INE): fuera; el INE solo publica cada punto en sus meses de
  temporada (F24).
- Pueblos prerromanos: las fronteras son territorios del punto más cercano de Pleiades, no límites históricos.
- Rendimiento: el primer dibujado tras cambiar de zoom bajó a la mitad (A26), pero con la CPU frenada ×4 sigue
  bloqueando de 0,5 a 0,9 s cuando el zoom cae en un cubo de sprites frío (pintar los sprites y planes de la escala
  nueva), y el margen que se pinta en tiempo libre puede retrasar una rueda que llegue justo entonces. Quedan el
  worker con OffscreenCanvas (sprites, mundo y capas registradas en otro hilo) o un relieve desde 8 px, que cambia la
  imagen; repintar por bandas se probó y se descartó (A18).
- La línea base de EE UU con datos frescos da 52 PASS y los datos publicados por Karpathy 51 PASS y 1 WARN; el repo
  sigue con los de Karpathy (D6).

## Más adelante

- **Parques nacionales como maravillas naturales en Unciv** (fase 2 del álbum, fuera de E89). Los datos están:
  `wonders.json` tiene los 16 parques con sus límites del OAPN y sus hexágonos, y un mod puede añadir terrenos
  `"type": "NaturalWonder"` en `jsons/Terrains.json` (`TileNormalizer` conserva el `naturalWonder` de una casilla si
  el ruleset lo tiene). Lo que cuesta, visto en el código de Unciv 5.0.1: el tileset por defecto es HexaRealm, con
  FantasyHex de reserva, y `TileLayerTerrain` se salta las imágenes que no existen, así que una maravilla sin imagen
  propia sale como un hexágono vacío; hacen falta 16 imágenes, o una registrada con 16 nombres, y el atlas de
  `pipeline/play.py` hoy guarda un icono por página. Rendimientos, `occursOn` y `turnsInto` de cada parque serían
  convenciones del juego nuevas, a explicar en las páginas de jugar; `unciv.without_mod` tendría que quitarlas del
  mapa sin mod y el arnés comprobar que cada maravilla sobrevive al editor. Toca los mismos ficheros que
  `feat/unciv-comunidades` (`spain_unciv.py`, `play.py`, traducciones del mod): mejor después de que esa rama entre.

## Publicación

- Despliegue del mapa a mano (`pipeline package --country es` y `wrangler pages deploy`, D16); automatizarlo cuando
  vuelvan los créditos de GitHub Actions.
- Publicar el anuncio en X (borrador preparado; lo publica David).

## Por decidir (David)

- Nombres de las comunidades en inglés: hoy van como los escribe el INE en los dos idiomas, como en el calendario de
  fiestas; pasar a «Catalonia», «Basque Country»… es un `tr()` en `community_name` (E89).
- Si los `web/data` de EE UU se regeneran con datos de hoy.
