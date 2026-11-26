# Changelog

Cambios de spainciv sobre usaciv de Andrej Karpathy (tag `upstream-2026-11-26`). Lo más reciente, arriba. Las
decisiones están en `DECISIONS.md`; lo pendiente, en `ROADMAP.md`.

## Sin publicar

### Añadido
- Lentes de Conocimiento, Vida diaria, Fe y Riesgos para España, equivalentes a las de EE UU con datos oficiales
  (E32–E38). **Banda ancha**: hogares con cobertura de 100 Mbps o más, por municipio (Ministerio para la
  Transformación Digital, junio de 2025; España 97,9 %). **Trabajan fuera**: ocupados que trabajan en otro municipio
  (Censo anual del INE, 2024; Madrid capital 28,6 %, el resto de su provincia 85,0 %). **Esperanza de vida** al nacer
  (INE, 2024; de 80,3 años en La Línea de la Concepción a 87,1 en Majadahonda). **Bodas religiosas**, proporción de los matrimonios
  (INE, 2025; España 16,1 %, de Girona 6,1 % a Jaén 38,5 %). **Incendios**: hectáreas quemadas por hexágono de 2016 a
  2025 según los perímetros del EFFIS (1,28 M ha). Las tres del INE llevan dato propio en unos 150 municipios y el del
  resto de su provincia en los demás. No hay lente de personas sin seguro médico: la sanidad pública es universal.
- Lentes de pobreza, edad media, nacidos en el extranjero, estudios superiores y vivienda en propiedad, con los iconos y grupos del mapa de EE. UU. Pobreza: residentes por debajo del 60 % de la mediana nacional de renta por unidad de consumo (Atlas de Distribución de Renta de los Hogares, 2024). Edad media: del mismo atlas (2024). Nacidos en el extranjero: Censo anual de población, 1 de enero de 2026. Estudios superiores: población de 15 años o más del Censo anual, 2024. Vivienda en propiedad: Censo de 2021. Madrid: 17,4 %, 43,9 años, 29,9 %, 46,8 %, 70,1 %; Zamora: 19,6 %, 48,7 años, 10,7 %, 35,6 %, 78,8 %. El valor de la vivienda sigue sin lente: no hay fuente municipal que lo dé por vivienda (E44).
- Lentes de fiesta. **Fiestas de interés turístico**: las 90 Internacionales y 164 Nacionales de la Secretaría de Estado de Turismo, con su nombre al pasar el ratón (Murcia tiene cuatro Internacionales: Semana Santa, Bando de la Huerta, Entierro de la Sardina y Moros y Cristianos). **Bares**: bares y pubs de OpenStreetMap por 1.000 habitantes (Benidorm, 5,3; Donostia y Salamanca, 2,5; Madrid, 0,7), con el aviso de que OSM cubre mucho mejor las ciudades que los pueblos. **Viviendas turísticas** por 1.000 habitantes, de la estadística experimental del INE (mayo de 2026: La Oliva 133, Roses 124, Nerja 123; España 6,9). **Índice de fiesta**, propio de este mapa: la media de los percentiles de fiestas, bares y viviendas turísticas (La Alberca, Llanes y Villajoyosa arriba). El grupo «Comida y bebida» pasa a «Comida, bebida y fiestas».
- Lentes de **castillos** (3.009) y **plazas de toros** (650) de Wikidata en el grupo de patrimonio, con sus nombres al pasar el ratón.
- Paro, renta de los hogares, alquiler y alquiler ÷ renta en las áreas urbanas, las provincias y España, con la comparación con España en cada panel. Paro: parados ÷ población activa del Censo anual del INE (2024). Renta: renta neta media por hogar del Atlas de Distribución de Renta de los Hogares (2024), rotulada como media. Alquiler: mediana mensual del SERPAVI del Ministerio de Vivienda (2024). Madrid: 8,0 %, 52.548 €, 844 € al mes; España: 11,5 %, 40.591 €, 620 €. El valor de la vivienda y el oro de las ciudades siguen vacíos por falta de fuente municipal (E30, E31).

### Corregido
- La potencia por provincia (consejero de Energía y Explorador) ya no sale vacía en España: `spain_resources` la
  rellena en `states.json` al terminar, con la misma suma que EE UU.
- Alejar el zoom ya no redibuja el mapa entero en cada fotograma: el lienzo se pinta al 60 % de la escala y se
  reescala hasta que el zoom para (de 11 a 4 redibujados en 20 pasos de rueda, en España y en EE UU).
- La vista de ciudad de España cita el Padrón, el Censo del INE y el atlas de áreas urbanas. Los distritos comparan
  con España y la sección de economía indica la escala provincial del PIB.
- Los enlaces compartidos abren la vista de ciudad aunque la cámara se actualice antes de cargar esa vista.
- El consejero de Energía y recursos sale en castellano en España: grupos, filtros, tabla de sitios y notas. Las
  notas de EE UU (umbrales, EIA, MSHA) solo salen allí; en España explican que las minas no tienen tamaño y hablan
  de provincias. Sin yacimientos de petróleo y gas no sale su tarjeta, y la potencia por provincia ya no da todas las
  provincias como «sin centrales» cuando faltan sus datos.

### Añadido
- La tarjeta social de spainciv (`og-image.png`) se dibuja desde los datos al empaquetar o servir
  (`pipeline/card.py`, Python puro): el mapa de hexágonos con su terreno, provincias, ríos, el recuadro de Canarias y
  las ciudades mayores, con el nombre, el título de la tarjeta, la dirección y la atribución del IGN. Sustituye al
  recorte de captura, que tenía los textos en inglés.
- El rendimiento de Ciencia es ahora el personal en I+D (en equivalencia a jornada completa) de la Estadística sobre
  actividades de I+D del INE, 2025: 310.336 personas en España en lugar de 1,9 M de ocupados en J + M. El INE lo da por
  comunidad; provincias y ciudades reciben su parte según sus ocupados en J + M (Censo). Gipuzkoa sube del puesto 16 al
  8 y Navarra del 21 al 12; Ceuta y Melilla quedan sin dato (secreto estadístico). Fuente nueva `ine_imasd`.
- Minas como recursos: las 25 explotaciones metálicas y de minerales industriales clave activas en 2019 según la
  Estadística Minera (IGME): cobre (Riotinto, Las Cruces, Aguas Teñidas, Cueva de la Mora, Sotiel), oro (El Valle-Boinás),
  wolframio (Los Santos), estaño y tántalo (Penouta), potasa, fluorita, celestina, magnesita y sulfato sódico. Están en
  su yacimiento del BDMIN del IGME (21) o en el centro de su municipio (4), sin valor: la estadística no publica la
  producción de cada mina.
- Capa «Platos regionales»: 577 platos, embutidos, quesos, dulces y vinos de las categorías de gastronomía por
  provincia de la Wikipedia en español, filtrados con Wikidata, listados en cada hexágono de su provincia.
- Interfaz de spainciv en castellano: tablas `web/js/i18n/<lang>/`, `t()`, números en es-ES (Intl) y textos de los
  datos de España en castellano (`texts_es.py`). El mapa de EE UU no cambia.
- Capa «Blue Flag beaches»: las 677 playas con Bandera Azul 2026-27, en los hexágonos de costa de su municipio y
  nombradas en el tooltip. ADEAC solo publica un PDF: `tools/bandera_azul_pdf.py` lo lee y cuadra cada comunidad.
- Capa «Languages»: dónde es oficial cada lengua, municipio a municipio según las leyes (catalán, aranés, valenciano
  con sus zonas castellanohablantes, gallego, euskera con la zona mixta de Navarra, asturiano protegido).
- Capa «Ancient peoples»: cada hexágono en el territorio del pueblo prerromano más cercano según Pleiades
  (Vaccaei, Vascones, Cantabri, Ilergetes, Turdetania…), sin que dos vecinos compartan color.
- Capa «Museums»: los 2.517 museos que Wikidata sitúa en España, contados por hexágono y nombrados en el tooltip.
- Capa «Food & drink»: las 292 denominaciones de calidad con zona (DOP, IGP, vinos de pago y de calidad) que cubren
  cada hexágono, con sus nombres al pasar el ratón (MAPA; España tiene 398 nombres en el registro de la UE).
- Recursos: centrales eléctricas en servicio (nucleares, hidráulicas, bombeo, ciclos combinados, carbón, fuel de
  las islas, y eólica, solar y baterías sumadas por hexágono), de powerplantmatching y, en Canarias, de OpenStreetMap.
- Universidades: las 20 presenciales con más alumnos (SIIU, curso 2024-25) como maravillas, en el municipio donde
  estudian más de sus alumnos. España no publica el gasto en I+D por universidad, así que se ordenan por alumnos.
- Visitantes de 2025 de los 16 Parques Nacionales (informe del OAPN, solo en PDF, transcrito a
  `pipeline/sources/es/data/`); los parques se ordenan por visitas, como en EE UU: el Teide, primero, con 5,1 M.
- Aeropuertos (los 48 de AENA, con su tráfico de 2025 y la categoría de hub de la FAA por cuota de pasajeros) y puertos
  (las 28 Autoridades Portuarias por toneladas de 2025) en el mapa.
### Corregido
- Los sitios de Patrimonio Mundial compartidos con otros países (hayedos, mercurio de Almadén) se colocan en su parte
  española, y los de costa (Torre de Hércules) ya no se pierden en el agua.
- Especialidades de la industria española en los distritos: calzado (Elda, «Shoe town»), textil (Alcoi), confección
  (A Coruña, «Fashion town»), bebidas (Logroño) y alimentación (Girona).
- Lente de patrimonio: Bienes de Interés Cultural por hexágono (15.634, Wikidata), en un grupo nuevo «Heritage».
- Maravillas repensadas: los 50 sitios de Patrimonio Mundial (la Alhambra, Altamira, la Mezquita…), los 16 Parques
  Nacionales y 81 catedrales, 144 en total, cada una con su dibujo (campanario, casco antiguo, cueva, palacio…).
  Fuente nueva `wikidata_es` (CC0).
- README propio de spainciv (inglés, con resumen en castellano) y capturas de España; el README de Karpathy pasa a
  `docs/USACIV.md`.
- Maravillas de España: los 16 Parques Nacionales (límites oficiales del OAPN), ordenados por superficie, con sus
  hexágonos protegidos (`spain_wonders`).
- Publicado en https://spainciv.djinnfoundry.com/ (Cloudflare Pages), con título, tarjetas sociales en español y
  og-image propios; `pipeline/site.py` escribe la página de cada país al servir o empaquetar, sin reconstruir datos.
- Línea de créditos en el mapa con la atribución del ANE (CC BY 4.0) y el crédito a usaciv; la imagen para compartir
  imprime las fuentes y la dirección del país.
- Carreteras (autovías y autopistas, carreteras principales) y ferrocarril de España sobre los hexágonos, con la regla
  de EE UU y Natural Earth 1:10m (`spain_infrastructure`). `build_roads` recibe la clasificación de cada país.
- Ciudades = las 86 grandes áreas urbanas del AUDES 2025 (Ministerio de Vivienda), como los metros de EE UU, con sus
  municipios miembros emparejados por nombre y comprobados contra el Padrón. El área de Madrid: 52 municipios, 6,6 M
  de habitantes. Lector XLSX con la biblioteca estándar (`core/xlsx.py`).
- Fronteras y capitales municipales del SIANE del IGN (CC BY 4.0, vía rOpenSpain/mapSpain) en lugar de GISCO LAU, que
  era solo de uso no comercial. Las ciudades están ahora en su capital municipal y el 100 % de la población cae en
  hexágonos. Lector de GeoPackage con la biblioteca estándar (`core/gpkg.py`).
- Distritos y tipos de ciudad de España con la regla de EE UU sobre el empleo del Censo por división CNAE (tabla 69980,
  151 ciudades; referencia nacional en la 69960). Catálogo CNAE propio (sin Encampment). Castelló sale «Ceramics
  city» (división 23), Valladolid «Motor city».
- Rendimientos Food, Production, Science y Culture, empleo por industria y ocupados de ciudades, provincias y nación.
  Salen del Censo anual del INE (ocupados por sección CNAE donde viven, 2024: tablas 69962 y 69992), traducido a las
  claves de industria de EE UU. Una primera versión con la afiliación a la Seguridad Social, que solo llegaba a
  provincias, se sustituyó por esta. En Castellón, la manufactura es la primera industria.
- Panel de provincia con los nombres del país: «Provincia», código INE, «rank among provincias».
- Lente de renta para España: renta neta media por persona del INE ADRH 2024 (tabla 30824), en euros.
- Primer mapa de España en `sites/es/data` (`pipeline serve --country es`):
  - 52 provincias y 8.132 municipios del SIANE (IGN) 2026;
  - relieve ETOPO1 y cubierta CORINE 2018;
  - 153 ciudades del Padrón 2025;
  - PIB provincial 2024.
- Fuentes de España en `pipeline/sources/es/`: `siane`, `etopo_es`, `natural_earth_es`, `corine`, `ine_padron`,
  `ine_pib`, `ine_adrh`.
- Builder `spain` (ciudades, provincias, nación y lentes), construido con los helpers de EE UU.
- Configuración por país (`pipeline/countries`, opción `--country us|es`) con proyección, hexágono, margen, niveles,
  moneda, regiones fuera del mapa, capital, umbrales de relieve y carpetas.
- Proyecciones en `core/geo.py`: LAEA esférica, LAEA elipsoidal (EPSG:3035) y recuadros (`InsetProjection`), con
  `to_web()` para el navegador.
- `web/js/geo.js`: invierte en el navegador la proyección de `world.json`. Un test con node comprueba que coincide con
  Python.
- Bloque `country` en `world.json`.
- Decodificador PNG con la biblioteca estándar (`core/png.py`).
- `fetch` admite una raíz de confianza extra por descarga.
- Tests: proyecciones (incluido el ejemplo de EPSG), países y registros, España, PNG, CORINE, INE y umbrales de relieve
  (de 176 a 227).
- `DECISIONS.md`, `ROADMAP.md`, `CHANGELOG.md`, `NOTICE`, `UPSTREAM.md` y `docs/SPAIN.md`.

### Cambiado
- Fuentes y builders van por país (`COUNTRIES`, `REQUIRES` por país); `world` recibe sus entradas por un adaptador.
- Las rutas de datos dependen del país activo; `store.load_web` sustituye a las lecturas a mano de `web/data`.
- `lenses`: el reparto de población y las lentes de suelo son funciones neutras.
- Web: el nombre, la URL, los niveles y la moneda salen de `world.json` (`$` o `€`, unidad `eur`). El panel de ciudad
  cita las fuentes de su país.
- Los carteles de ciudad se rotulan según la escala del mapa, no según el tamaño del hexágono.
- `world`: umbrales de relieve por país, regiones más pequeñas que un hexágono, rangos de río enteros.
- `package` empaqueta el producto del país activo con sus datos.

### Arreglado
- `DECISIONS.md` ya no lleva rutas locales ni nombres de equipos (va dentro del zip de código público).
- Licencia: el sitio empaquetado lleva `LICENSE` y `NOTICE` (antes solo dentro del zip de código), la ayuda de
  spainciv da el crédito a usaciv y el README dice que es un fork.
- El nombre de la imagen compartida convertía la ñ y los acentos en guiones (apuntado en `UPSTREAM.md`).

### Verificado
- EE UU: los 15 ficheros de `web/data` salen idénticos byte a byte a los del original con la misma caché, salvo el
  bloque `country` de `world.json`.
