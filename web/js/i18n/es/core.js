// Spanish interface strings: the page chrome (index.html), top bar, tooltips, city and province panels, lens dock and
// legend, help and Almanac (see web/js/i18n.js). Written for the Spanish map (spainciv).
export default {
  // index.html (i18n.js PAGE_STRINGS)
  "page.yields": "Rendimientos nacionales",
  "page.search.placeholder": "Buscar ciudad o provincia",
  "page.search.label": "Buscar ciudades y provincias (/ o Ctrl K)",
  "page.share.label": "Compartir esta vista",
  "page.share.title": "Compartir: copiar un enlace o descargar una imagen",
  "page.help.label": "Ayuda de teclado y ratón",
  "page.help.title": "Ayuda (?)",
  "page.pedia.label": "Abrir el Almanaque",
  "page.pedia.title": "Qué significa cada cifra y de dónde sale",
  "page.panel": "Detalles",
  "page.lensPicker": "Elegir una lente",
  "page.legend": "Leyenda de la lente",
  "page.lensDock": "Lentes del mapa",
  "page.res.label": "Recursos en las casillas (R)",
  "page.res.title": "Mostrar u ocultar los recursos de las casillas (R)",
  "page.minimap": "Minimapa: haz clic para saltar",
  "page.minimap.show": "Mostrar el minimapa",
  "page.searchResults": "Resultados de la búsqueda",
  "page.sharePop": "Compartir",
  "page.report": "Informe nacional",
  "page.pedia": "Almanaque",
  "page.pedia.close": "Cerrar el Almanaque",
  "page.pedia.nav": "Páginas del Almanaque",
  "page.loading": "Cartografiando el territorio…",

  // top bar
  "core.topbar.tip": "{name}: {description} Haz clic para ver el informe.",
  "core.topbar.aria": "{name}: {value}. Abrir el informe",
  "core.turn": "Turno <b>{year}</b> · {vintage}",

  // tooltips
  "core.people": "{n} habitantes",
  "core.hexes": { one: "{n} hexágono", other: "{n} hexágonos" },
  "core.tip.deep": "{n} m de profundidad",
  "core.tip.water": "Agua",
  "core.tip.land": "Tierra",
  "core.tip.foreign": "Más allá de las fronteras (fuera del mapa)",
  "core.tip.more": "y {n} más",
  "core.tip.openCity": "Haz clic para abrir la ciudad",
  "core.tip.openState": "Haz clic para abrir {name}",

  // city and province panels
  "core.panel.city": "Ciudad",
  "core.panel.close": "Cerrar el panel (Esc)",
  "core.panel.closeTitle": "Cerrar (Esc)",
  "core.panel.almanac": "Almanaque ›",
  "core.panel.open": "Abrir {name}",
  "core.panel.capital": "Capital de España",
  "core.panel.yields": "Rendimientos",
  "core.panel.yieldsRank": "Rendimientos · posición entre las {levels}",
  "core.panel.amenities": "Servicios y vivienda",
  "core.panel.districts": "Distritos · dónde trabaja la gente",
  "core.panel.topIndustries": "Principales sectores · dónde trabaja la gente",
  "core.panel.biggestCities": "Ciudades más grandes",
  "core.panel.data": "Datos",
  "core.panel.noStates": "Estos datos no traen estadísticas provinciales (falta states.json).",
  "core.panel.noCities": "Esta provincia no tiene áreas urbanas en los datos.",
  "core.panel.code": "INE {code}",
  "core.panel.cityFoot": "Fuente: {vintage}{gdp}; paro del Censo anual de población del INE, renta del ADRH del INE y alquiler del SERPAVI (Ministerio de Vivienda). ×N en verde: la proporción de ocupados del sector es N veces la de España. Los campos que aún no tienen fuente para España salen como –.",
  "core.panel.stateFoot": "Fuente: {vintage}{gdp}; paro del Censo anual de población del INE, renta del ADRH del INE y alquiler del SERPAVI (Ministerio de Vivienda). La posición es entre las {count} {levels} del mapa (1 = la mayor).",
  "core.panel.gdpSource": "; PIB: {vintage}",
  "core.panel.yieldSource": "; {label}: {vintage}",
  "core.panel.gdpLabel": "PIB",
  "core.panel.gdpYear": "PIB ({year})",
  "core.panel.perPerson": "{value} por habitante",
  "core.panel.rank": "{rank}.º de {count}",
  "core.panel.rankTitle": "Posición entre las {count} {levels} del mapa (1 = la mayor)",
  "core.panel.nation": "España {value}",
  "core.panel.unemployment": "Paro",
  "core.panel.income": "Renta neta media por hogar",
  "core.panel.homeValue": "Valor mediano de la vivienda",
  "core.panel.rent": "Alquiler mediano / mes",
  "core.panel.rentBurden": "Alquiler ÷ renta",
  "core.panel.noIndustries": "Sin datos de empleo por sector.",
  "core.panel.lqTip": "La proporción de ocupados es {lq} veces la nacional",
  "core.panel.pop": "<b>{pop}</b> habitantes · {employed} ocupados{extra}",
  "core.growth.lastYears": "los últimos años",
  "core.growth.nation": " (España {value})",
  "core.growth.tip": "Variación de la población {period}, Padrón del INE: {value}{nation}",
  "core.growth.since": "desde {year}",

  // lens dock and legend
  "core.lens.terrain": "Terreno",
  "core.lens.lensTitle": "Lente {name}",
  "core.lens.noLensTitle": "{name} (sin lente)",
  "core.lens.lenses": "Lentes",
  "core.lens.allTitle": "Todas las lentes (L las recorre)",
  "core.lens.other": "Otras",
  "core.lens.choose": "Elige una lente",
  "core.lens.closePicker": "Cerrar el selector de lentes",
  "core.lens.baseMap": "Mapa base",
  "core.lens.noData": "sin datos",
  "core.lens.perKm2": " /km²",
  "core.lens.minutes": "{n} min",
  "core.lens.years": "{n} años",
  "core.lens.showFull": "Ver la leyenda completa",
  "core.lens.details": "Detalles",
  "core.lens.off": "Quitar la lente (volver al terreno)",
  "core.lens.backToTerrain": "Volver al terreno",
  "core.lens.categories": "Categorías de {name}: haz clic en una para ver solo esa",
  "core.lens.catHint": "Haz clic en una categoría para ver solo esa",
  "core.lens.showingOnly": "Solo {what}",
  "core.lens.allValues": "todos los valores",
  "core.lens.scaleLabel": "Resalta un tramo de valores de {name}. Pasa el ratón o arrastra; las flechas mueven el resalte y Escape lo quita.",
  "core.lens.scaleHint": "Pasa el ratón o arrastra sobre la escala para ver solo ese tramo",
  "core.lens.higherBetter": "▲ Más es mejor",
  "core.lens.higherWorse": "▲ Más es peor",

  // help (app/help.js)
  "core.help.title": "Controles",
  "core.help.close": "Cerrar la ayuda",
  "core.help.move": "Moverse",
  "core.help.explore": "Explorar",
  "core.help.panels": "Paneles",
  "core.help.key.drag": "Arrastrar",
  "core.help.key.scroll": "Rueda",
  "core.help.key.doubleClick": "Doble clic",
  "core.help.key.twoFingers": "Dos dedos",
  "core.help.key.minimap": "Minimapa",
  "core.help.key.clickCity": "Clic en ciudad",
  "core.help.key.clickLand": "Clic en tierra",
  "core.help.key.legend": "Leyenda",
  "core.help.key.shiftL": "Mayús L",
  "core.help.pan": "Desplazar el mapa",
  "core.help.zoom": "Acercar y alejar",
  "core.help.zoomSpot": "Acercar a un punto",
  "core.help.pinch": "Pellizcar para acercar, arrastrar para desplazar (táctil)",
  "core.help.jump": "Clic o arrastre para saltar",
  "core.help.openCity": "Abrir la pantalla de la ciudad",
  "core.help.openState": "Abrir esa provincia",
  "core.help.search": "Buscar ciudades y provincias",
  "core.help.lens": "Lente siguiente / anterior",
  "core.help.resources": "Mostrar u ocultar los recursos",
  "core.help.help": "Esta ayuda",
  "core.help.esc": "Cerrar la ayuda, la búsqueda, el Almanaque y después el panel",
  "core.help.foot": "Cada cifra remite a datos públicos: abre el <b>Almanaque</b> para ver las fuentes.\n      El enlace de la barra de direcciones vuelve a abrir siempre esta misma vista.\n      Código fuente: {zip} (MIT; se ejecuta con uv, véase su README).",
  "core.help.basedOn": "\n      {product} está basado en {usaciv}, de Andrej Karpathy (licencia MIT, véase LICENSE).",

  // Almanac (ui/pedia.js)
  "core.pedia.about": "Sobre este mapa",
  "core.pedia.about.body": `<p>Esta es la España real, dibujada como un juego de estrategia. No hay nada inventado: cada casilla, ciudad y
      cifra sale de datos públicos, que se citan en <i>Fuentes</i>.</p>
      <h4>Cómo está hecho</h4>
      <p>España se proyecta con una azimutal equivalente de Lambert centrada en la península, con Canarias en un recuadro
      al suroeste, y se divide en {cols}×{rows} hexágonos de {km} km de vértice a vértice. Cada hexágono pertenece a la
      provincia y al municipio que hay bajo su centro. El terreno sale de las muestras de altitud de cada hexágono.</p>
      <p>Las <b>ciudades</b> son las 86 grandes áreas urbanas del Atlas Digital de las Áreas Urbanas (más de 50.000
      habitantes), situadas en la capital de su municipio principal. Sus cifras suman todos los municipios del área, no
      solo el de la ciudad.</p>
      <h4>Controles</h4>
      <p>Arrastra o usa las flechas / WASD para desplazarte · rueda, +/– o doble clic para acercar · clic en una ciudad o
      una provincia para abrirla · / o ⌘K para buscar · L para cambiar de lente · R para mostrar u ocultar los recursos ·
      ? para todos los atajos · Esc para cerrar.</p>
      <p>La barra de direcciones guarda siempre un enlace a lo que estás viendo (lente, selección y vista); usa
      <i>Compartir</i> para copiarlo o para descargar una imagen.</p>`,
  "core.pedia.yields": "Rendimientos",
  "core.pedia.yields.intro": `<p>Los rendimientos de Civilization trasladados a medidas reales. Los que salen del empleo cuentan a los
      <i>residentes</i> ocupados en un sector (donde vive quien trabaja, no donde trabaja). <b>El oro es el PIB</b>: lo
      que se produce en un año, contado donde se hace el trabajo.</p>`,
  "core.pedia.yields.amenities": `<h4>Servicios y vivienda</h4>
      <p>El paro, la renta mediana de los hogares, el alquiler y el valor de la vivienda aún no tienen una fuente municipal
      en España, así que ciudades y provincias los muestran como –.</p>`,
  "core.pedia.states.body": `<p>Haz clic en cualquier hexágono de tierra sin ciudad para abrir su provincia. Las cifras de una provincia son
      los totales provinciales de las mismas fuentes que las ciudades ({vintage}{gdp}), no la suma de sus ciudades, así
      que el mundo rural también cuenta.</p>
      <p>Las <b>posiciones</b> («3.º de 52») comparan las 50 provincias y las ciudades autónomas de Ceuta y Melilla; 1 es
      la mayor.</p>
      <p>Un área urbana que cruza un límite provincial aparece en todas las provincias que toca, con las cifras del área
      entera.</p>`,
  "core.pedia.states.gdp": "; PIB de {vintage}",
  "core.pedia.states.none": "Estos datos no traen states.json, así que los paneles de provincia solo muestran el nombre y las ciudades.",
  "core.pedia.terrain": "Terreno",
  "core.pedia.terrain.intro": `<p>Cada hexágono promedia las muestras de altitud de ETOPO1 que caen dentro. El relieve sale de la altitud
      media y de la rugosidad (desviación típica) de esas muestras; el sombreado, de las diferencias de altitud con los
      hexágonos vecinos, con la luz desde el noroeste.</p>`,
  "core.pedia.terrain.cover": "Cubierta del suelo",
  "core.pedia.terrain.coverBody": `<p>El color de base de cada hexágono es su grupo de cubierta dominante: el mayor entre las muestras de tierra
      que contiene. Unos símbolos pequeños muestran la mezcla: los árboles crecen con la proporción de bosque, y campos,
      juncos, arbustos y matas de hierba marcan cultivos, humedales, matorral y pastizal.</p>`,
  "core.pedia.terrain.noCover": "Estos datos aún no tienen capa de cubierta del suelo; la tierra se colorea por altitud.",
  "core.pedia.terrain.relief": "Relieve",
  "core.pedia.terrain.water": "Agua",
  "core.pedia.terrain.beyond": "Más allá de las fronteras",
  "core.pedia.terrain.beyondBody": `Las tierras extranjeras (Portugal, Francia, Andorra y Marruecos) se dibujan bajo una niebla ligera: están
      como contexto y no se cartografían en detalle.`,
  "core.pedia.lenses.intro": `<p>Las lentes colorean el mapa según una medida, construida con datos municipales ({vintage}). Cada hexágono
      se muestrea en 7 puntos, y un municipio que cubre algunos de ellos cubre esa parte del hexágono. Un municipio tan
      pequeño que no lo toca ninguna muestra se suma al hexágono que contiene su centro. La renta se promedia entre los
      municipios de cada hexágono, ponderada por población.</p>
      <p>La leyenda muestra cuántos hexágonos caen en cada valor. Pasa el ratón o arrastra sobre ella para ver solo ese
      tramo en el mapa.</p>`,
  "core.pedia.lenses.scale": "Escala: {scale}, {from}–{to} {unit}",
  "core.pedia.scale.log": "logarítmica",
  "core.pedia.scale.linear": "lineal",
  "core.pedia.lenses.better": " · más es mejor",
  "core.pedia.lenses.worse": " · más es peor",
  "core.pedia.resources": "Recursos",
  "core.pedia.resources.none": "Estos datos no tienen capa de recursos.",
  "core.pedia.resources.intro": `<p>Los recursos señalan las mayores centrales eléctricas, minas y yacimientos de petróleo y gas del país en
      las casillas donde están. Solo se muestran los lugares relevantes: el umbral de cada tipo está en su descripción.
      Con el mapa alejado, cada hexágono enseña su recurso más importante; acércate para ver más. Pulsa <b>R</b> para
      mostrarlos u ocultarlos.</p>`,
  "core.pedia.resources.type": "Tipo",
  "core.pedia.resources.counts": "Qué cuenta",
  "core.pedia.resources.sites": "Lugares",
  "core.pedia.resources.unit": "valor en {unit}",
  "core.pedia.cat.energy": "Energía",
  "core.pedia.cat.mineral": "Minerales",
  "core.pedia.cat.agri": "Agricultura",
  "core.pedia.source": "Fuente: {name}",
  "core.pedia.sources": "Fuentes",
  "core.pedia.homepage": "web",
};
