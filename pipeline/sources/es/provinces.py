"""Spain's 52 provinces (50 plus the autonomous cities of Ceuta and Melilla): INE code → (ISO 3166-2:ES code, name).

Reference data, not a download: the INE province codes are the first two digits of every municipality code, and
the ISO 3166-2:ES subdivision codes are the short labels the map uses where a full name doesn't fit. Names are the
official ones (co-official spellings as INE publishes them).
"""

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


def display_name(name: str) -> str:
    """INE's inverted article form → reading order: 'Coruña, A' → 'A Coruña', 'Balears, Illes' → 'Illes Balears'."""
    if ", " in name:
        rest, article = name.rsplit(", ", 1)
        if len(article.split()) == 1 and article[:1].isupper() and len(article) <= 5:
            return f"{article} {rest}"
    return name
