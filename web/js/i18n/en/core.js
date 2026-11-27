// English interface strings: the page chrome (index.html), top bar, tooltips, city and state panels, lens dock and
// legend, help and Almanac (see web/js/i18n.js). These are usaciv's original texts.
export default {
  // index.html (i18n.js PAGE_STRINGS)
  "page.yields": "National yields",
  "page.search.placeholder": "Search cities & states",
  "page.search.label": "Search cities and states (/ or Ctrl K)",
  "page.share.label": "Share this view",
  "page.share.title": "Share: copy a link or download an image",
  "page.help.label": "Keyboard and mouse help",
  "page.help.title": "Help (?)",
  "page.pedia.label": "Open the Almanac",
  "page.pedia.title": "What every number means and where it comes from",
  "page.panel": "Details",
  "page.lensPicker": "Choose a lens",
  "page.legend": "Lens legend",
  "page.lensDock": "Map lenses",
  "page.res.label": "Resources on tiles (R)",
  "page.res.title": "Show or hide resources on tiles (R)",
  "page.minimap": "Minimap: click to jump",
  "page.minimap.show": "Show the minimap",
  "page.searchResults": "Search results",
  "page.sharePop": "Share",
  "page.report": "National report",
  "page.pedia": "Almanac",
  "page.pedia.close": "Close the Almanac",
  "page.pedia.nav": "Almanac pages",
  "page.loading": "Surveying the land…",

  // top bar
  "core.topbar.tip": "{name}: {description} Click for the report.",
  "core.topbar.aria": "{name}: {value}. Open the report",
  "core.turn": "Turn <b>{year}</b> · {vintage}",

  // tooltips
  "core.people": "{n} people",
  "core.hexes": { one: "{n} hex", other: "{n} hexes" },
  "core.tip.deep": "{n} m deep",
  "core.tip.water": "Water",
  "core.tip.land": "Land",
  "core.tip.foreign": "Beyond the borders (not mapped)",
  "core.tip.more": "+{n} more",
  "core.tip.openCity": "Click to open the city",
  "core.tip.openState": "Click to open {name}",

  // city and state panels
  "core.panel.city": "City",
  "core.panel.close": "Close panel (Esc)",
  "core.panel.closeTitle": "Close (Esc)",
  "core.panel.almanac": "Almanac ›",
  "core.panel.open": "Open {name}",
  "core.panel.capital": "National capital",
  "core.panel.yields": "Yields",
  "core.panel.yieldsRank": "Yields · rank among {levels}",
  "core.panel.amenities": "Amenities &amp; Housing",
  "core.panel.districts": "Districts · where people work",
  "core.panel.topIndustries": "Top industries · where people work",
  "core.panel.biggestCities": "Biggest cities",
  "core.panel.data": "Data",
  "core.panel.noStates": "State statistics are not in this data build (states.json is missing).",
  "core.panel.noCities": "No metro or micro areas in this state's data.",
  "core.panel.code": "FIPS {code}",
  "core.panel.cityFoot": "Source: {vintage} (tables C24030, B19025, B19013, B25064, B25077, B23025){gdp}.\n      Green ×N = this industry's share of jobs is N× the U.S. share.",
  "core.panel.stateFoot": "Source: {vintage}{gdp}. Ranks are among the {count} mapped {levels} + DC (1 = largest).",
  "core.panel.gdpSource": "; GDP: {vintage}",
  "core.panel.yieldSource": "; {label}: {vintage}",
  "core.panel.gdpLabel": "GDP",
  "core.panel.gdpYear": "GDP ({year})",
  "core.panel.perPerson": "{value} per person",
  "core.panel.rank": "#{rank} of {count}",
  "core.panel.rankTitle": "Rank among the {count} mapped {levels} (1 = largest)",
  "core.panel.nation": "US {value}",
  "core.panel.unemployment": "Unemployment",
  "core.panel.income": "Median household income",
  "core.panel.homeValue": "Median home value",
  "core.panel.rent": "Median gross rent / mo",
  "core.panel.rentBurden": "Rent ÷ income",
  "core.panel.noIndustries": "No industry data.",
  "core.panel.lqTip": "Share of jobs is {lq}× the national share",
  "core.panel.pop": "<b>{pop}</b> people · {employed} employed{extra}",
  "core.growth.lastYears": "the last few years",
  "core.growth.nation": " (U.S. {value})",
  "core.growth.tip": "Population change {period}, Census population estimates: {value}{nation}",
  "core.growth.since": "since {year}",

  // lens dock and legend
  "core.lens.terrain": "Terrain",
  "core.lens.lensTitle": "{name} lens",
  "core.lens.noLensTitle": "{name} (no lens)",
  "core.lens.lenses": "Lenses",
  "core.lens.allTitle": "All lenses (L cycles)",
  "core.lens.other": "Other",
  "core.lens.choose": "Choose a lens",
  "core.lens.closePicker": "Close lens picker",
  "core.lens.baseMap": "Base map",
  "core.lens.noData": "no data",
  "core.lens.perKm2": " /km²",
  "core.lens.minutes": "{n} min",
  "core.lens.duration": "{h} h {m} min",
  "core.lens.hours": "{n} h",
  "core.lens.years": "{n} yrs",
  "core.lens.showFull": "Show the full legend",
  "core.lens.details": "Details",
  "core.lens.off": "Turn the lens off (back to terrain)",
  "core.lens.backToTerrain": "Back to terrain",
  "core.lens.categories": "{name} categories: click one to show only it",
  "core.lens.catHint": "Click a category to show only it",
  "core.lens.showingOnly": "Showing only {what}",
  "core.lens.allValues": "all values",
  "core.lens.scaleLabel": "Highlight a range of {name} values. Hover or drag; arrow keys move the highlight, Escape clears it.",
  "core.lens.scaleHint": "Hover or drag the scale to show only that range",
  "core.lens.higherBetter": "▲ Higher is better",
  "core.lens.higherWorse": "▲ Higher is worse",

  // help (app/help.js)
  "core.help.title": "Controls",
  "core.help.close": "Close help",
  "core.help.move": "Move",
  "core.help.explore": "Explore",
  "core.help.panels": "Panels",
  "core.help.key.drag": "Drag",
  "core.help.key.scroll": "Scroll",
  "core.help.key.doubleClick": "Double-click",
  "core.help.key.twoFingers": "Two fingers",
  "core.help.key.minimap": "Minimap",
  "core.help.key.clickCity": "Click city",
  "core.help.key.clickLand": "Click land",
  "core.help.key.legend": "Legend",
  "core.help.key.shiftL": "Shift L",
  "core.help.pan": "Pan the map",
  "core.help.zoom": "Zoom in and out",
  "core.help.zoomSpot": "Zoom in on a spot",
  "core.help.pinch": "Pinch to zoom, drag to pan (touch)",
  "core.help.jump": "Click or drag to jump",
  "core.help.openCity": "Open the city screen",
  "core.help.openState": "Open that state",
  "core.help.search": "Search cities and states",
  "core.help.lens": "Next / previous lens",
  "core.help.resources": "Show or hide resources",
  "core.help.help": "This help",
  "core.help.esc": "Close help, search, Almanac, then the panel",
  "core.help.foot": "Every number traces back to public data: open the <b>Almanac</b> for sources.\n      The link in the address bar always reopens this exact view.\n      Source code: {zip} (MIT; run it with uv, see its README).",
  "core.help.basedOn": "\n      {product} is based on {usaciv} by Andrej Karpathy (MIT licence, see LICENSE).",
  "core.help.play": "\n      This map can be played in Unciv, the open-source Civilization V: {link}.",
  "core.help.playLink": "Play in Unciv",
  // Almanac (ui/pedia.js)
  "core.pedia.about": "About this map",
  "core.pedia.about.body": `<p>This is the real United States, drawn like a strategy game. Nothing is invented: every tile, city and
      number comes from public data, listed under <i>Sources</i>.</p>
      <h4>How it's built</h4>
      <p>The lower 48 states are projected (Albers equal-area) and cut into {cols}×{rows}
      hexes, each {km} km corner to corner. Each hex belongs to the state and county under its centre.
      Terrain comes from elevation samples inside each hex.</p>
      <p><b>Cities</b> are the metropolitan and micropolitan areas published in the ACS 1-year estimates (the Census Bureau
      includes areas of roughly 65,000+ people, so a few now fall slightly below that), placed at their principal city. Their numbers cover the whole metro area, not just the city proper.</p>
      <h4>Controls</h4>
      <p>Drag or arrow keys / WASD to pan · scroll, +/– or double-click to zoom · click a city or a state to open it ·
      / or ⌘K to search · L to cycle lenses · R to show or hide resources · ? for all shortcuts · Esc to close.</p>
      <p>The address bar always holds a link to what you're looking at (lens, selection and view); use <i>Share</i> to copy it
      or to download a picture.</p>`,
  "core.pedia.yields": "Yields",
  "core.pedia.yields.intro": `<p>Civilization's yields mapped onto real measures. Job-based yields count <i>residents</i> employed in an industry
      (where workers live, not where they work). <b>Gold is GDP</b>: output per year, counted where the work is done.</p>`,
  "core.pedia.yields.amenities": `<h4>Amenities &amp; housing</h4>
      <p>Unemployment = unemployed ÷ civilian labour force (B23025). Rent ÷ income = median gross rent × 12 ÷ median household
      income: a rough affordability signal, not a household-level burden rate.</p>`,
  "core.pedia.states.body": `<p>Click any land hex without a city to open its state. A state's numbers are the state totals and medians from the
      same tables as the cities ({vintage}{gdp}),
      not the sum of its cities, so rural areas count too.</p>
      <p><b>Ranks</b> ("#3 of 49") compare the 48 contiguous states and the District of Columbia; 1 is the largest. Alaska,
      Hawaii and the territories are not mapped yet, so they are not ranked.</p>
      <p>Metro areas that cross state lines (New York–Newark, Kansas City, Philadelphia…) are listed under every state they
      touch, with their whole-metro numbers.</p>`,
  "core.pedia.states.gdp": "; GDP from {vintage}",
  "core.pedia.states.none": "This data build has no states.json, so state panels show names and cities only.",
  "core.pedia.terrain": "Terrain",
  "core.pedia.terrain.intro": `<p>Each hex averages the ETOPO1 elevation samples inside it. Relief comes from the mean elevation and roughness
      (standard deviation) of those samples; shading comes from elevation differences with neighbouring hexes, lit from the
      north-west.</p>`,
  "core.pedia.terrain.cover": "Land cover",
  "core.pedia.terrain.coverBody": `<p>The base colour of each hex is its dominant land-cover group: the largest group among the land samples inside it.
           Small symbols show the mix: trees scale with the forest share, and fields, reeds, shrubs and grass tufts mark farmland,
           wetland, scrub and grassland.</p>`,
  "core.pedia.terrain.noCover": "This data build has no land-cover layer yet; land is coloured by elevation.",
  "core.pedia.terrain.relief": "Relief",
  "core.pedia.terrain.water": "Water",
  "core.pedia.terrain.beyond": "Beyond the borders",
  "core.pedia.terrain.beyondBody": `Foreign land (Canada, Mexico, and in the Caribbean Cuba and the Bahamas) is drawn under a light fog:
      it is shown for context and not mapped in detail.`,
  "core.pedia.lenses.intro": `<p>Lenses recolour the map by one measure, built from county data ({vintage}). Each hex is sampled
      at 7 points. A county covering some of them is assumed to cover that share of the hex. Small dense counties that no
      sample hits (Manhattan, Virginia's independent cities) are added to the hex containing their centre. Income and home
      value are averaged over the counties in a hex, weighted by population.</p>
      <p>The legend shows how many hexes fall at each value. Hover or drag on it to show only that range on the map.</p>`,
  "core.pedia.lenses.scale": "Scale: {scale}, {from}–{to} {unit}",
  "core.pedia.scale.log": "log",
  "core.pedia.scale.linear": "linear",
  "core.pedia.lenses.better": " · higher is better",
  "core.pedia.lenses.worse": " · higher is worse",
  "core.pedia.resources": "Resources",
  "core.pedia.resources.none": "This data build has no resources layer.",
  "core.pedia.resources.intro": `<p>Resources mark the country's biggest power plants, mines and oil &amp; gas fields on the tiles where they are.
      Only meaningful sites are shown: each type's threshold is in its description. When zoomed out, a hex shows its
      highest-ranked resource; zoom in to see more. Press <b>R</b> to show or hide them.</p>`,
  "core.pedia.resources.type": "Type",
  "core.pedia.resources.counts": "What counts",
  "core.pedia.resources.sites": "Sites",
  "core.pedia.resources.unit": "value in {unit}",
  "core.pedia.cat.energy": "Energy",
  "core.pedia.cat.mineral": "Minerals",
  "core.pedia.cat.agri": "Agriculture",
  "core.pedia.source": "Source: {name}",
  "core.pedia.sources": "Sources",
  "core.pedia.homepage": "homepage",
};
