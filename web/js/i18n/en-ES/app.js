// Spain in English: the app strings that differ from the US English (web/js/i18n/en/app.js).
export default {
  // yield reports
  "report.population.desc": "Registered residents (INE municipal Padrón).",
  "report.unemp.desc": "Unemployed ÷ labour force.",
  "report.metrosMin": "{metros} of {min} or more",
  "report.scope.note": {
    one: "Ranks the {what}; {outside} counts in the national total but is not ranked.",
    other: "Ranks the {what}; {outside} count in the national total but are not ranked.",
  },
  "report.pop.growth": "{g}{since} (INE Padrón)",
  "report.pop.hint": "Population change{since}; {metros} of {min} residents or more.",
  "report.unemp.large": "Large {metros} ({min} or more)",
  "report.unemp.hint": "{Metros} of {min} residents or more.",
  "report.gold.year": "Year {y}, current euros",
  "report.gold.hint": "{years}; {metros} of {min} residents or more.",
  "report.jobs.hint": "The area's share of employed residents in {y} ÷ the national share ({p}); {metros} of {min} residents or more.",

  // search
  "search.none": "No city, province or person matches “{q}”",

  // map
  "map.aria": "Hex map of Spain",
  "map.loadError": "Could not load the map data ({error}). Run \"uv run python -m pipeline all --country es\" and serve the site over HTTP.",

  // map layers and their tooltips
  "layers.hubs.title": "Main ports and airports",
  "layers.military.title": "Military installations as forts, and the largest training areas",
  "layers.trade.title": "The largest road freight flows between autonomous communities (EPTMC)",
  "tip.port.note": "Total freight of the Port Authority (Puertos del Estado), placed at its largest port.",
  "tip.port.foreign": "International {foreign} · domestic {domestic}",
  "tip.port.rank": "#{rank} by tonnage · <b>{tons}</b> t ({year})",
  "tip.air.note": "Passengers (arrivals plus departures) and freight, from AENA.",
  "tip.air.cargoOnly": "Cargo-only airport",
  "tip.air.cargo": "{v} t of freight",

  // what the Spanish says that the US English does not
  "map.layers.title": "Map layers: roads, rail and more",
  "layers.roads.title": "Motorways, dual carriageways and main roads (Natural Earth, as map art)",
  "layers.wonders.title": "World Heritage sites, National Parks, great universities and cathedrals",
  "wonder.rank": "{kind} · #{rank}{among}",
  "wonder.students": "<b>{n}</b> students ({year} academic year)",
  "wonder.visits": "<b>{n}</b> visitors ({year})",
  "wonder.amongOther": " among protected areas",
  "tip.hub.N": "No hub category",
  "tip.air.pax": "<b>{n}</b> passengers in {year}{change}",
  "tip.fort.site": "Military installation",
  "tip.fort.joint": " · joint use",
};
