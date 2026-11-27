// Spain in English: the core strings that differ from the US English (web/js/i18n/en/core.js).
export default {
  // index.html (i18n.js PAGE_STRINGS)
  "page.search.placeholder": "Search cities, provinces or people",
  "page.search.label": "Search cities, provinces and people (/ or Ctrl K)",

  // city and province panels
  "core.panel.noStates": "This data has no province statistics (states.json is missing).",
  "core.panel.noCities": "This province has no urban areas in the data.",
  "core.panel.cityFoot": "Source: {vintage}{gdp}; unemployment from INE's Annual Population Census, income from INE's ADRH and rent from SERPAVI (Ministry of Housing). Green ×N: the industry's share of employed residents is N times Spain's. Fields that have no source for Spain yet show as –.",
  "core.panel.stateFoot": "Source: {vintage}{gdp}; unemployment from INE's Annual Population Census, income from INE's ADRH and rent from SERPAVI (Ministry of Housing). The rank is among the {count} {levels} on the map (1 = largest).",
  "core.panel.nation": "Spain {value}",
  "core.panel.capital": "Capital of Spain",
  "core.panel.code": "INE {code}",
  "core.panel.income": "Mean net household income",
  "core.panel.rent": "Median rent / mo",
  "core.growth.nation": " (Spain {value})",
  "core.growth.tip": "Population change {period}, INE Padrón: {value}{nation}",

  // help
  "core.help.openState": "Open that province",
  "core.help.search": "Search cities, provinces and people",

  // Almanac
  "core.pedia.about.body": `<p>This is the real Spain, drawn like a strategy game. Nothing is invented: every tile, city and
      number comes from public data, listed under <i>Sources</i>.</p>
      <h4>How it's built</h4>
      <p>Spain is projected with a Lambert azimuthal equal-area projection centred on the peninsula, with the Canary
      Islands in an inset to the south-west, and cut into {cols}×{rows} hexes, each {km} km corner to corner. Each hex
      belongs to the province and municipality under its centre. Terrain comes from elevation samples inside each hex.</p>
      <p><b>Cities</b> are the 86 large urban areas of the Atlas Digital de las Áreas Urbanas (more than 50,000
      residents), placed at the capital of their main municipality. Their numbers add up every municipality in the area,
      not just the city's own.</p>
      <h4>Controls</h4>
      <p>Drag or arrow keys / WASD to pan · scroll, +/– or double-click to zoom · click a city or a province to open it ·
      / or ⌘K to search · L to cycle lenses · R to show or hide resources · ? for all shortcuts · Esc to close.</p>
      <p>The address bar always holds a link to what you're looking at (lens, selection and view); use <i>Share</i> to copy it
      or to download a picture.</p>`,
  "core.pedia.states.body": `<p>Click any land hex without a city to open its province. A province's numbers are the
      provincial totals from the same sources as the cities ({vintage}{gdp}), not the sum of its cities, so rural areas
      count too.</p>
      <p><b>Ranks</b> ("3rd of 52") compare the 50 provinces and the autonomous cities of Ceuta and Melilla; 1 is the
      largest.</p>
      <p>An urban area that crosses a provincial border is listed under every province it touches, with the numbers of
      the whole area.</p>`,
  "core.pedia.states.none": "This data has no states.json, so province panels show only the name and the cities.",
  "core.pedia.terrain.beyondBody": `Foreign land (Portugal, France, Andorra and Morocco) is drawn under a light fog: it is
      shown for context and not mapped in detail.`,
  "core.pedia.lenses.intro": `<p>Lenses recolour the map by one measure. Nearly all are built from municipal data
      ({vintage}): each hex is sampled at 7 points, and a municipality covering some of them covers that share of the hex. A municipality so
      small that no sample hits it is added to the hex containing its centre. Income is averaged over the municipalities
      in a hex, weighted by population. A few are worked out in the browser, such as the fiesta calendar or Sun and clock,
      and their descriptions say where each value comes from.</p>
      <p>The legend shows how many hexes fall at each value. Hover or drag on it to show only that range on the map.</p>`,
  "core.pedia.yields.amenities": `<h4>Amenities &amp; housing</h4>
      <p>Unemployment = unemployed ÷ (employed + unemployed), from INE's Annual Population Census, counted where people live.
      Income = mean net income per household from INE's Household Income Distribution Atlas (ADRH): a mean, because INE
      publishes no median per household for municipalities. Rent = median monthly rent of the whole dwelling from SERPAVI
      (Ministry of Housing); flats and houses, and the municipalities of an urban area, are combined as the mean of their
      medians weighted by rented dwellings. Rent ÷ income = rent × 12 ÷ household income: a rough signal of what renting
      costs, not each household's burden. The value of a dwelling has no source by municipality and shows as –; the
      home value lens gives each province's appraised value in €/m².</p>`,
};
