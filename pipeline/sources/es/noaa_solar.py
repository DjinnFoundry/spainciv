"""NOAA's solar calculator: the equations of the sun's position (after Meeus) that the sun lens (web/js/ext/sun/solar.js)
evaluates in the browser. There is no data to process: `fetch` caches the page that gives the equations and the
calculator's own code, which tests/test_sun_js.py's reference times come from, so the Almanac cites what was used.
Rules: DECISIONS.md E84.
"""

from __future__ import annotations

from ...core.source import Source, SourceInfo

FILES = {
    "calcdetails.html": "https://gml.noaa.gov/grad/solcalc/calcdetails.html",
    "main.js": "https://gml.noaa.gov/grad/solcalc/main.js",
}


class NoaaSolar(Source):
    info = SourceInfo(
        id="noaa_solar",
        title="NOAA Solar Calculator: solar position equations (Solar Calculation Details)",
        publisher="NOAA Global Monitoring Laboratory",
        homepage="https://gml.noaa.gov/grad/solcalc/calcdetails.html",
        license="Public domain (U.S. Government work)",
        description="The equations NOAA's solar calculator uses for the sun's declination and the equation of time, "
        "from Jean Meeus, Astronomical Algorithms, with sunrise and sunset when the sun's centre is 0.833° below a "
        "sea-level horizon. NOAA gives them as accurate in theory to within a minute between ±72° of latitude; "
        "observed times vary with the atmosphere. The map evaluates them in the browser for each hex's centre.",
        used_for=["Sun and clock lens (sunrise, sunset, solar noon, daylight)"],
    )

    def fetch(self, force=False):
        for name, url in FILES.items():
            self.download(url, name, force=force)

    def process(self):
        return {"_files": sorted(FILES)}
