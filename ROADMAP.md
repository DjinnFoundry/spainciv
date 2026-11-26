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
- El oro de las ciudades queda vacío: no hay PIB municipal oficial, y la renta o las bases del IRPF no lo sustituyen (E31).
- Valor de la vivienda: no hay valor por vivienda municipal abierto; el valor tasado del Ministerio está en €/m² y en XLS binario (E30). Por decidir si entra como campo propio.
- La renta de los hogares es una media (el INE no publica la mediana municipal) y el alquiler de un área es la media de medianas municipales ponderada por contratos (E27, E29).
- Los campos de los consejeros apuntan a los ids de fuente de EE UU (`acs_1yr`, `bea_gdp`) también en España.
- Los ciudadanos de la City View y los ejércitos, el comercio y los desastres siguen siendo solo de EE UU.
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
- Pueblos prerromanos: las fronteras son territorios del punto más cercano de Pleiades, no límites históricos.
- Rendimiento: arrastrar y el primer dibujado tras cambiar de zoom siguen bloqueando 40–115 ms con la CPU frenada
  ×4 (opciones: relieve desde 8 px, lienzo más ancho hacia el arrastre, teselas o worker).
- La línea base de EE UU con datos frescos da 52 PASS y los datos publicados por Karpathy 51 PASS y 1 WARN; el repo
  sigue con los de Karpathy (D6).

## Publicación

- Despliegue del mapa a mano (`pipeline package --country es` y `wrangler pages deploy`, D16); automatizarlo cuando
  vuelvan los créditos de GitHub Actions.
- Publicar el anuncio en X (borrador preparado; lo publica David).

## Por decidir (David)

- Si los `web/data` de EE UU se regeneran con datos de hoy.
