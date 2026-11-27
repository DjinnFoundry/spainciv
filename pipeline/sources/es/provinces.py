"""Spain's 52 provinces (50 plus the autonomous cities of Ceuta and Melilla): INE code → (ISO 3166-2:ES code, name),
and the autonomous communities they belong to.

Reference data, not a download: the INE province codes are the first two digits of every municipality code, and
the ISO 3166-2:ES subdivision codes are the short labels the map uses where a full name doesn't fit. Names are the
official ones (co-official spellings as INE publishes them).
"""

from ...core.lang import tr

PROVINCES = {
    "01": ("VI", "Araba/Álava"), "02": ("AB", "Albacete"), "03": ("A", "Alicante/Alacant"), "04": ("AL", "Almería"),
    "05": ("AV", "Ávila"), "06": ("BA", "Badajoz"), "07": ("PM", "Balears, Illes"), "08": ("B", "Barcelona"),
    "09": ("BU", "Burgos"), "10": ("CC", "Cáceres"), "11": ("CA", "Cádiz"), "12": ("CS", "Castellón/Castelló"),
    "13": ("CR", "Ciudad Real"), "14": ("CO", "Córdoba"), "15": ("C", "Coruña, A"), "16": ("CU", "Cuenca"),
    "17": ("GI", "Girona"), "18": ("GR", "Granada"), "19": ("GU", "Guadalajara"), "20": ("SS", "Gipuzkoa"),
    "21": ("H", "Huelva"), "22": ("HU", "Huesca"), "23": ("J", "Jaén"), "24": ("LE", "León"), "25": ("L", "Lleida"),
    "26": ("LO", "Rioja, La"), "27": ("LU", "Lugo"), "28": ("M", "Madrid"), "29": ("MA", "Málaga"), "30": ("MU", "Murcia"),
    "31": ("NA", "Navarra"), "32": ("OR", "Ourense"), "33": ("O", "Asturias"), "34": ("P", "Palencia"),
    "35": ("GC", "Palmas, Las"), "36": ("PO", "Pontevedra"), "37": ("SA", "Salamanca"), "38": ("TF", "Santa Cruz de Tenerife"),
    "39": ("S", "Cantabria"), "40": ("SG", "Segovia"), "41": ("SE", "Sevilla"), "42": ("SO", "Soria"),
    "43": ("T", "Tarragona"), "44": ("TE", "Teruel"), "45": ("TO", "Toledo"), "46": ("V", "Valencia/València"),
    "47": ("VA", "Valladolid"), "48": ("BI", "Bizkaia"), "49": ("ZA", "Zamora"), "50": ("Z", "Zaragoza"),
    "51": ("CE", "Ceuta"), "52": ("ML", "Melilla"),
}


# Autonomous communities (17, plus the autonomous cities of Ceuta and Melilla): INE code → (name as INE writes it, its
# provinces). Copied from the community and province columns of INE table 69962 (Annual Population Census).
COMMUNITIES = {
    "01": ("Andalucía", ["04", "11", "14", "18", "21", "23", "29", "41"]), "02": ("Aragón", ["22", "44", "50"]),
    "03": ("Asturias, Principado de", ["33"]), "04": ("Balears, Illes", ["07"]), "05": ("Canarias", ["35", "38"]),
    "06": ("Cantabria", ["39"]), "07": ("Castilla y León", ["05", "09", "24", "34", "37", "40", "42", "47", "49"]),
    "08": ("Castilla - La Mancha", ["02", "13", "16", "19", "45"]), "09": ("Cataluña", ["08", "17", "25", "43"]),
    "10": ("Comunitat Valenciana", ["03", "12", "46"]), "11": ("Extremadura", ["06", "10"]),
    "12": ("Galicia", ["15", "27", "32", "36"]), "13": ("Madrid, Comunidad de", ["28"]), "14": ("Murcia, Región de", ["30"]),
    "15": ("Navarra, Comunidad Foral de", ["31"]), "16": ("País Vasco", ["01", "20", "48"]), "17": ("Rioja, La", ["26"]),
    "18": ("Ceuta", ["51"]), "19": ("Melilla", ["52"]),
}
COMMUNITY_OF = {prov: comm for comm, (_, provs) in COMMUNITIES.items() for prov in provs}

# Each community as the interface names it, in reading order, in Spanish and English, the same keys as COMMUNITIES
# (INE's names above are the ones its tables match on). Data from a source keeps the name its source writes: the
# fiestas name their community as each community's own list does (fiestas_autonomicas.COMMUNITIES, "Catalunya",
# "Principado de Asturias"), since they are a transcription of those lists.
COMMUNITY_NAMES = {
    "01": tr("Andalucía", "Andalusia"), "02": tr("Aragón", "Aragon"), "03": tr("Asturias", "Asturias"),
    "04": tr("Illes Balears", "Balearic Islands"), "05": tr("Canarias", "Canary Islands"),
    "06": tr("Cantabria", "Cantabria"), "07": tr("Castilla y León", "Castile and León"),
    "08": tr("Castilla-La Mancha", "Castilla–La Mancha"), "09": tr("Cataluña", "Catalonia"),
    "10": tr("Comunitat Valenciana", "Valencian Community"), "11": tr("Extremadura", "Extremadura"),
    "12": tr("Galicia", "Galicia"), "13": tr("Comunidad de Madrid", "Community of Madrid"),
    "14": tr("Región de Murcia", "Region of Murcia"), "15": tr("Navarra", "Navarre"),
    "16": tr("País Vasco", "Basque Country"), "17": tr("La Rioja", "La Rioja"), "18": tr("Ceuta", "Ceuta"),
    "19": tr("Melilla", "Melilla"),
}
# The name a label uses where the full one doesn't fit, the full one where it already does.
COMMUNITY_SHORT_NAMES = {
    **COMMUNITY_NAMES, "04": tr("Baleares", "Balearics"), "05": tr("Canarias", "Canaries"),
    "10": tr("C. Valenciana", "Valencia region"), "13": tr("Madrid", "Madrid"), "14": tr("Murcia", "Murcia"),
}


def display_name(name: str) -> str:
    """INE's inverted article form → reading order: 'Coruña, A' → 'A Coruña', 'Balears, Illes' → 'Illes Balears'."""
    if ", " in name:
        rest, article = name.rsplit(", ", 1)
        if len(article.split()) == 1 and article[:1].isupper() and len(article) <= 5:
            return f"{article} {rest}"
    return name


def community_name(code: str) -> str:
    """A community's INE name in reading order: 'Madrid, Comunidad de' → 'Comunidad de Madrid', 'Rioja, La' → 'La
    Rioja'; the rest as INE writes it ('Castilla - La Mancha')."""
    name = COMMUNITIES[code][0]
    if ", " in name:
        rest, article = name.rsplit(", ", 1)
        if article.endswith(" de"):
            return f"{article} {rest}"
    return display_name(name)
