# Changelog

Cambios de spainciv sobre usaciv de Andrej Karpathy (tag `upstream-2026-11-26`). Lo más reciente, arriba. Las
decisiones están en `DECISIONS.md`; lo pendiente, en `ROADMAP.md`.

## Sin publicar

### Añadido
- **Personajes en el tiempo** («¿Quién vivía en 1520?»): dos lentes nuevas junto a las de grandes personajes,
  «Personajes vivos en {año}» y «Oficios en {año}», con un panel para elegir el año (de Argantonio, 670 a. C., a
  hoy), avanzar por décadas o siglos y reproducir desde el año 50. Cada hexágono con alguien vivo lleva un punto que
  crece con la gente; sin nadie, queda gris. En el año 1000 viven 24 de los personajes del mapa, 15 en Córdoba; en
  1520, 347, con 117 conquistadores (32 de ellos con alguna fecha que Wikidata da solo por década o siglo, que cuenta
  entera); en 2000, 3.093. Cuenta a quien vivía ese año, no a quien había nacido. 83 de los 6.119 se quedan fuera por
  fechas que faltan o no casan, entre ellos quienes Wikidata da por muertos sin fecha utilizable. El enlace guarda el
  año (`#lens=great_people_year&anio=1000`; `anio=-201` es 201 a. C.). Solo en el mapa de España, en sus dos idiomas
  (E87, E88, A28).
- **Grandes personajes**: los pilotos de automovilismo y de motociclismo salen como deportistas cuando su descripción
  de Wikidata lo dice (Fernando Alonso salía como «actor» porque Wikidata también le da ese oficio), y quien Wikidata
  da por muerto sin fecha lleva «1915–?» en vez de «n. 1915».
- **Adivina el hexágono, pistas que se pueden seguir**. El hexágono del día ya no es un pueblo cualquiera con
  gente: tiene al menos dos cosas con nombre propio (una fiesta, un castillo, una maravilla, un museo, una central, un
  personaje famoso, una denominación de origen pequeña…). Las pistas van de la zona de España y la distancia al mar a
  un río, la lengua y el pueblo prerromano; la tercera ya nombra algo de allí, la cuarta sitúa el hexágono respecto a
  una ciudad del mapa y la quinta la nombra. Los recuentos de patrimonio salen solo si no son cero. El día 1 pasa a ser
  Guadix; una partida guardada con otro hexágono vuelve a empezar (E82, E83).
- **Calendario de fiestas** («¿Dónde hay fiesta este mes?»), en el selector de lentes junto a la de fiestas: elige un mes y el mapa pinta los hexágonos con fiesta ese mes, del color de su categoría, con la fecha que da la fuente en el tooltip; el panel las lista por categoría y nombre y lleva a cada una en el mapa. Las que no tienen mes conocido (610 de 1.296) se cuentan aparte. Una fiesta Internacional o Nacional toma las fechas de su declaración autonómica, si la tiene. El enlace guarda el mes (`#lens=fiestas_mes&mes=8`). En castellano e inglés; el mapa de EE. UU. no lo tiene (E80, E81).
- Capa **Bandera Azul**: cada playa va en el hexágono donde está. 604 de las 677 casan por nombre y municipio con
  Wikidata (518) u OpenStreetMap (86); las 73 que no casan siguen repartidas por la costa de su municipio, como antes.
  Antes las playas de un municipio se turnaban entre sus hexágonos de costa sin mirar dónde estaba cada una: las de
  Vigo caían en uno y ahora en cuatro; 6 de las 15 de embalse o río de interior dejan el centro del pueblo. El tooltip
  da playa y municipio (E74, E75, F33).
- **Adivina el hexágono**, el juego del día (botón en la barra superior, o el enlace `#juego`). Seis pistas sobre un
  hexágono de 10 km sacadas de los datos del mapa (terreno, gente, renta, lengua, patrimonio y, al final, la inicial de
  la provincia, quién nació allí y qué se come); seis intentos con la distancia y una flecha; el resultado se copia o
  se comparte sin desvelar el lugar. Guarda la partida del día y la racha en el navegador. En castellano e inglés; el
  mapa de EE. UU. no lo tiene (A25, E76).
- **Fiestas autonómicas** en la lente de fiestas: 1.042 fiestas que declaran de interés turístico 15 comunidades
  autónomas, cada una con su nombre (Fiesta de Interés Turístico de Andalucía, Festa de Interese Turístico de Galicia,
  Fiesta de Interés Turístico Regional de Castilla-La Mancha…), de la lista oficial de cada comunidad. Pasan a
  sumar 0,5 puntos en el índice de fiesta. `fiestas.json` guarda todas las fiestas con sus fechas, donde la fuente las
  da (798 de 1.296), para un calendario futuro. Euskadi, Illes Balears, Ceuta y Melilla no declaran ninguna
  (E77–E79, F34).
- **spainciv en inglés**. El mapa se abre en el idioma del navegador (inglés si el navegador lo prefiere; si no,
  castellano). Un botón pequeño al final de la barra superior cambia de idioma, el sitio recuerda la elección y el
  enlace que se comparte la lleva (`#lang=en`).
  - Interfaz, lentes, Almanaque, consejeros, fuentes, maravillas, recursos, distritos, personajes y la página de
    Unciv (`play.html`) están en los dos idiomas.
  - Los nombres propios se quedan como los escribe su fuente.
  - Los números siguen al idioma: «1,6 B €» en castellano y «€1.6T» en inglés.
  - Las capas inglesas pesan unos 80 kB comprimidas, 38 kB sin la de personajes, que solo se carga al abrir sus
    lentes. No repiten ningún valor (A20–A24, E72).
- Los ficheros de datos que España no tiene (los del Ejército y del comercio de EE. UU.) ya no se piden, así que
  desaparecen los dos 404 de la consola.
- Mapa de Unciv: el uranio y el aluminio buscan su casilla hasta unos 50 km del yacimiento (3 casillas de uranio y
  1 de aluminio). Los yacimientos del BDMIN con coordenadas en metros UTM (27 de 280) quedan en su sitio: el carbón de
  Villablino, el oro de Salave y la bauxita de La Vansa ya están en el mapa (E63).
- Capa **Denominaciones de origen** con los 398 nombres que España tiene en el registro de la UE (eran 292 zonas del
  Ministerio de 2017): 108 con zona nueva, entre ellos los 43 vinos de la tierra, 14 vinos de pago y lo registrado desde 2017
  (Torrezno de Soria, Miel de Málaga, Queso de Burgos…), con la zona de su documento único o pliego sobre los límites
  municipales; el tooltip dice cómo se obtuvo cada zona. Penedès, Priorat, Idiazabal, los txakolis y otros que no
  casaban por el nombre quedan enlazados a su registro. En el mapa de Unciv, el vino pasa de 81 a 132 casillas
  (E64–E66, F31).
- **Ejército** para España: el General deja de estar vacío. 478 instalaciones militares de OpenStreetMap (23 grandes,
  75 bases), con su rama (Tierra, Armada, Aire y del Espacio, UME), su superficie y su enlace a Wikidata; los 15 mayores
  campos de maniobras como terreno restringido (San Gregorio, 338 km²; Chinchilla, 149; Sierra del Retín, 100); las
  instalaciones y el terreno militar por provincia; y 29 ciudades con guarnición. Rota y Morón van marcadas como de uso
  conjunto con Estados Unidos. La capa militar del mapa dibuja sus fuertes y campos. Sin efectivos ni gasto por
  provincia: el anuario de Defensa no se pudo descargar (E67–E71, A19, F32).
- **Jugar en Unciv**: España como mapa de Unciv (la versión libre de Civilization V), con mod descargable, mapa suelto
  y una página que explica cómo instalarlo en el ordenador y en Android y qué es dato real y qué convención del juego
  (enlazada desde la ayuda). 83 × 53 casillas de 25 km con la costa, el relieve, los bosques, los ríos y la cubierta del
  suelo del mapa; recursos de datos: vino en 81 denominaciones de origen, sal, mármol, piedra, hierro y petróleo de las
  explotaciones del IGME, cobre y oro de sus minas, ganado, ovejas, pescado, cítricos y especias de sus IGP y DOP. El
  Peñón de Gibraltar es la maravilla natural. España empieza en Madrid y los demás en las grandes áreas urbanas.
  Probado en Unciv 5.0.1: el mod se instala desde su enlace, el mapa se abre en el editor y una partida de 40 turnos
  corre sobre él (E51–E57).
- **Grandes personajes**: 6.119 personas famosas nacidas en la España actual, de Wikidata, en el hexágono de su lugar de nacimiento, en 19 categorías al estilo de los grandes personajes de Civilization (de premios Nobel y conquistadores a cantantes y deportistas) con un umbral de fama cada una (E58, E59, F27). Dos lentes: personajes por hexágono y categoría con más personajes; la ayuda emergente da nombre, oficio y fechas («Pablo Picasso (pintor, 1881–1973)»). El buscador encuentra a las personas y por su pueblo: «Cervantes» lleva a Alcalá de Henares.
- Mapa de Unciv: carbón, uranio, hierro, oro, plata y cobre de los yacimientos grandes y medianos del BDMIN del IGME,
  se exploten o no; caballos en las 20 comarcas con más équidos por km² del Censo Agrario 2020; y un recurso propio
  del mod, el **cerdo ibérico**, en las cuatro DOP de jamón ibérico. El mod pasa a ser de extensión y Unciv lo activa
  al elegir el mapa; el mapa suelto es el mismo sin el cerdo. El README del mod está en castellano e inglés. Probado
  de nuevo en Unciv 5.0.1 (E60–E62).
- Lente de **valor de la vivienda** por provincia: valor tasado de la vivienda libre del Ministerio de Vivienda, 2.º trimestre de 2026 (España 2.355 €/m²; de Ciudad Real, 854, a Madrid, 4.090). Va en €/m²: no hay fuente con el valor de una vivienda entera.
- Lentes de Conocimiento, Vida diaria, Fe y Riesgos para España, equivalentes a las de EE UU con datos oficiales
  (E32–E38). **Banda ancha**: hogares con cobertura de 100 Mbps o más, por municipio (Ministerio para la
  Transformación Digital, junio de 2025; España 97,9 %). **Trabajan fuera**: ocupados que trabajan en otro municipio
  (Censo anual del INE, 2024; Madrid capital 28,6 %, el resto de su provincia 85,0 %). **Esperanza de vida** al nacer
  (INE, 2024; de 80,3 años en La Línea de la Concepción a 87,1 en Majadahonda). **Bodas religiosas**, proporción de los matrimonios
  (INE, 2025; España 16,1 %, de Girona 6,1 % a Jaén 38,5 %). **Incendios**: hectáreas quemadas por hexágono de 2016 a
  2025 según los perímetros del EFFIS (1,28 M ha). Las tres del INE llevan dato propio en unos 150 municipios y el del
  resto de su provincia en los demás. No hay lente de personas sin seguro médico: la sanidad pública es universal.
- Lentes de pobreza, edad media, nacidos en el extranjero, estudios superiores y vivienda en propiedad, con los iconos y grupos del mapa de EE. UU. Pobreza: residentes por debajo del 60 % de la mediana nacional de renta por unidad de consumo (Atlas de Distribución de Renta de los Hogares, 2024). Edad media: del mismo atlas (2024). Nacidos en el extranjero: Censo anual de población, 1 de enero de 2026. Estudios superiores: población de 15 años o más del Censo anual, 2024. Vivienda en propiedad: Censo de 2021. Madrid: 17,4 %, 43,9 años, 29,9 %, 46,8 %, 70,1 %; Zamora: 19,6 %, 48,7 años, 10,7 %, 35,6 %, 78,8 %. El valor de la vivienda sigue sin lente: no hay fuente municipal que lo dé por vivienda (E44).
- Lentes de fiesta. **Fiestas de interés turístico**: las 90 Internacionales y 164 Nacionales de la Secretaría de Estado de Turismo, con su nombre al pasar el ratón (Murcia tiene cuatro Internacionales: Semana Santa, Bando de la Huerta, Entierro de la Sardina y Moros y Cristianos). **Bares**: bares y pubs de OpenStreetMap por 1.000 habitantes (Benidorm, 5,3; Donostia y Salamanca, 2,5; Madrid, 0,7), con el aviso de que OSM cubre mucho mejor las ciudades que los pueblos. **Viviendas turísticas** por 1.000 habitantes, de la estadística experimental del INE (mayo de 2026: La Oliva 133, Roses 124, Nerja 123; España 6,9). **Índice de fiesta**, propio de este mapa: cuántas veces lo habitual en España tiene un hexágono de bares, viviendas turísticas y fiestas, como media geométrica, con lo habitual en oscuro (Sallent de Gállego, Peñíscola, Llanes y Naut Aran arriba). El grupo «Comida y bebida» pasa a «Comida, bebida y fiestas».
- Lentes de **castillos** (3.009) y **plazas de toros** (650) de Wikidata en el grupo de patrimonio, con sus nombres al pasar el ratón.
- Paro, renta de los hogares, alquiler y alquiler ÷ renta en las áreas urbanas, las provincias y España, con la comparación con España en cada panel. Paro: parados ÷ población activa del Censo anual del INE (2024). Renta: renta neta media por hogar del Atlas de Distribución de Renta de los Hogares (2024), rotulada como media. Alquiler: mediana mensual del SERPAVI del Ministerio de Vivienda (2024). Madrid: 8,0 %, 52.548 €, 844 € al mes; España: 11,5 %, 40.591 €, 620 €. El valor de la vivienda y el oro de las ciudades siguen vacíos por falta de fuente municipal (E30, E31).

### Corregido
- Tras cada despliegue, quien ya había visitado el mapa seguía hasta 4 horas con los scripts viejos y los datos nuevos (Cloudflare Pages guarda JS y CSS 4 horas). El paquete de España lleva ahora un `_headers` que los hace revalidar en cada visita, como la página y los datos.
- Grandes personajes, descargados de nuevo: Tenesor Semidán entra como guanarteme de Gran Canaria (con el cargo que se le añadió en Wikidata) y Francesco Redi sale del mapa (nació en Arezzo; Wikidata lo situaba en Lugo). El título propio de los reyes guanches gana a la palabra de la descripción.
- Los nombres que una fuente da en mayúsculas (fiestas autonómicas de Galicia, Asturias, Castilla-La Mancha y Valencia) salen como se escriben en castellano, con la «i» catalana en minúscula («Moros i Cristians») y los artículos gallegos en mayúscula («de O Carballiño»).
- Las descargas reintentan también el HTTP 429 (demasiadas peticiones), esperando lo que pida la cabecera `Retry-After` del servidor, hasta 5 minutos. La de grandes personajes se cortaba en Wikidata.
- Denominaciones: el mapa del Ministerio archiva Mongeta del Ganxet con el código del Cordero de Extremadura y Siurana con el de Les Garrigues, y el cordero extremeño salía en Barcelona y Girona. Cada zona va ahora con su nombre, y Mongeta del Ganxet y Siurana toman el polígono del Ministerio en vez de su lista de municipios.
- Nombres de las áreas urbanas con guion o barra como se escriben («Tarragona-Reus», «Alcoy/Alcoi», «Vitoria/Gasteiz») y
  «Santa Cruz de Tenerife - La Laguna», que el AUDES escribe «Salta Cruz» (E73).
- El Almanaque ya no dice que el paro, la renta y el alquiler no tienen fuente municipal en España: explica de dónde sale
  cada uno (E27–E29) y que el valor de una vivienda sigue sin fuente por municipio.
- Arrastrar el mapa se engancha menos: al entrar terreno nuevo se pinta solo la franja que aparece, no el
  mapa entero (con la CPU frenada ×4, de 104 a 22 ms por repintado a ×2,5; A18).
- El zoom se engancha menos al asentarse: se pinta primero lo que se ve y el resto de la caché después, los planes del
  relieve se reutilizan entre zooms parecidos y se precalientan dos y tres muescas de rueda. Con la CPU frenada ×4, tres
  muescas desde la vista inicial dejan el fotograma más largo en 859 ms (antes 1575), y desde ×2,5 en 575 (antes 1342;
  A26).
- Los reyes guanches de Tenerife salen como «mencey» en vez de «monarca», con el cargo que les da Wikidata; un guanarteme de Gran Canaria saldría igual con el suyo.
- Mayúsculas de los nombres como se escriben en castellano: «Palma de Mallorca», «Jerez de la Frontera», «Torre de Garay», «FGL Granada-Jaén», en aeropuertos, centrales, minas y lugares de Wikidata. Los aeropuertos pierden las marcas de nota de AENA («(**)») y los helipuertos salen como «Ceuta (helipuerto)».
- Museos y castillos sin nombre en castellano toman el gallego, catalán o euskera antes que el inglés (antes salían 19 en inglés; quedan 12, que Wikidata solo nombra en inglés).
- La franja de créditos nombra las fuentes nuevas: MITECO, MAPA, AENA, Puertos del Estado, IGME, Wikidata y OpenStreetMap.
- Consejeros de España sin gráficos vacíos ni «0 puntos» (E50): Economía muestra el empleo por sector y pone el mapa
  de PIB, la clasificación y el gráfico de crecimiento por provincias; Prosperidad compara la renta con el alquiler
  anual; el Explorador quita las columnas sin datos y abre con renta frente a crecimiento; Cultura oculta la sección
  de desastres cuando no hay datos.
- La potencia por provincia (consejero de Energía y Explorador) ya no sale vacía en España: `spain_resources` la
  rellena en `states.json` al terminar, con la misma suma que EE UU.
- Restos de inglés y de EE UU en el mapa de España: los tooltips de puertos y aeropuertos («Large hub», «short tons»,
  FAA, USACE), 103 nombres de centrales («Las Majas Wind Farm» pasa a «Parque eólico Las Majas»), las fechas de cinco
  fuentes («AENA 2025 (final)», «students», «visitors») y textos de los consejeros que hablaban de embarques, libras,
  el NPS o la I+D de las facultades de medicina. Los puertos y la carga aérea se dan en toneladas, no en toneladas
  cortas ni en libras (Algeciras: 100,7 M t, no 111 M). El menú Mapa ya no ofrece Ejército ni Rutas comerciales, que
  España no tiene. Un test busca palabras inglesas en `sites/es/data` para que no vuelvan.
- `pipeline serve` se reinicia cuando cambia el código del pipeline. Un servidor arrancado antes de traducir la página
  servía la línea de créditos en inglés bajo la interfaz en castellano; `package` y `serve` dan ya el mismo `index.html`.
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
