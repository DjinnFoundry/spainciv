# Changelog

Cambios de spainciv sobre usaciv de Andrej Karpathy (tag `upstream-2026-11-26`). Lo más reciente, arriba. Las
decisiones están en `DECISIONS.md`; lo pendiente, en `ROADMAP.md`.

## Sin publicar

### Corregido
- La vista de ciudad de España cita el Padrón, el Censo del INE y el atlas de áreas urbanas. Los distritos comparan
  con España y la sección de economía indica la escala provincial del PIB.

### Añadido
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
