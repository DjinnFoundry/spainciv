# Roadmap

Lo que falta para spainciv, por orden de valor. Al terminar algo se borra de aquí y se apunta en `CHANGELOG.md`; las
decisiones que salgan van a `DECISIONS.md`.

## Ahora

1. **Revisión de David** de las decisiones marcadas «Claude» en `DECISIONS.md`.

## Después

2. I+D por comunidad (estadística de I+D del INE) para el rendimiento Science.
4. Centrales (REE / registro del MITECO) y minas (IGME): recursos.
6. **i18n en/es**: pasada completa de la interfaz (unas 550 líneas en inglés en el JS), en un subagente en paralelo.

## Huecos conocidos

- El oro de las ciudades queda vacío: no hay PIB municipal oficial.
- Mediana de renta por hogar, alquiler, valor de la vivienda y paro de las ciudades: sin fuente municipal todavía.
- Los ciudadanos de la City View y los ejércitos, el comercio y los desastres siguen siendo solo de EE UU.
- Distritos: describen el municipio núcleo de cada área (5 de las 86 áreas tienen un núcleo sin divisiones CNAE en el
  Censo y se quedan sin distritos); los municipios no tienen distritos propios. Sin Encampment (defensa no se separa a
  dos dígitos).
- Empleo de las áreas: sin los miembros de menos de 500 habitantes (tres áreas, unos 6.500 residentes).
- El Padrón 2025 tiene 8.138 municipios y el SIANE 2026 8.132.
- 298 hexágonos de mar, sobre todo alrededor del recuadro de Canarias, no tienen muestras de ETOPO (bajo el recuadro se descartan a propósito).
- En la vista inicial, el minimapa tapa parte del recuadro de Canarias.
- La línea base de EE UU con datos frescos da 52 PASS y los datos publicados por Karpathy 51 PASS y 1 WARN; el repo
  sigue con los de Karpathy (D6).

## Publicación

- Despliegue del mapa a mano (`pipeline package --country es` y `wrangler pages deploy`, D16); automatizarlo cuando
  vuelvan los créditos de GitHub Actions.
- Publicar el anuncio en X (borrador preparado; lo publica David).
- Generar la og-image desde código en vez de un recorte de captura.

## Por decidir (David)

- Si los `web/data` de EE UU se regeneran con datos de hoy.
