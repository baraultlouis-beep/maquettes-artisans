#!/usr/bin/env python3
"""
Scrape les artisans (plombiers, électriciens, couvreurs, paysagistes,
menuisiers) sur OpenStreetMap via l'API Overpass, et génère un fichier
prospects.json directement compatible avec generer_maquettes.py.

À exécuter sur ta machine (ce container n'a pas accès à Internet vers OSM).

Usage :
    python scraper_artisans.py --departement 35 --metier plombier
    python scraper_artisans.py --departement 35,22,56 --metier tous

Coût : 0 € (API Overpass gratuite, pas de clé requise). Respecte un délai
entre les requêtes pour ne pas surcharger le serveur public.
"""

import argparse
import json
import sys
import time
import urllib.request

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Tag OSM correspondant à chaque métier (shop=* ou craft=*)
TAGS_PAR_METIER = {
    "plombier": ['"craft"="plumber"'],
    "electricien": ['"craft"="electrician"'],
    "couvreur": ['"craft"="roofer"'],
    "paysagiste": ['"shop"="garden_centre"', '"craft"="gardener"'],
    "menuisier": ['"craft"="carpenter"'],
}

# Codes département -> nom de zone OSM (area) pour restreindre la recherche
NOMS_DEPARTEMENTS = {
    "35": "Ille-et-Vilaine",
    "22": "Côtes-d'Armor",
    "56": "Morbihan",
    "29": "Finistère",
}


def construire_requete(departement: str, tags: list) -> str:
    zone = NOMS_DEPARTEMENTS.get(departement, departement)
    filtres = "".join(f'  node[{tag}](area.zone);\n  way[{tag}](area.zone);\n' for tag in tags)
    return f"""
[out:json][timeout:60];
area["name"="{zone}"]["boundary"="administrative"]->.zone;
(
{filtres}
);
out center tags;
"""


def interroger_overpass(requete: str) -> dict:
    data = requete.encode("utf-8")
    req = urllib.request.Request(OVERPASS_URL, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=90) as reponse:
        return json.loads(reponse.read().decode("utf-8"))


def extraire_prospect(element: dict, metier: str) -> dict | None:
    tags = element.get("tags", {})
    nom = tags.get("name")
    if not nom:
        return None  # on ignore les fiches sans nom, inutilisables pour un mail personnalisé

    ville = tags.get("addr:city", "")
    telephone = tags.get("contact:phone") or tags.get("phone", "")
    email = tags.get("contact:email") or tags.get("email", "")
    site_existant = tags.get("website") or tags.get("contact:website", "")

    prospect = {
        "nom": nom,
        "ville": ville,
        "telephone": telephone,
        "email": email,
        "metier": metier,
    }
    if site_existant:
        prospect["_site_existant"] = site_existant  # à exclure : il a déjà un site
    return prospect


def scraper_metier(departement: str, metier: str) -> list:
    tags = TAGS_PAR_METIER[metier]
    requete = construire_requete(departement, tags)
    print(f"  Interrogation OSM : {metier} / dept {departement}...")
    resultat = interroger_overpass(requete)

    prospects = []
    for element in resultat.get("elements", []):
        p = extraire_prospect(element, metier)
        if p:
            prospects.append(p)
    return prospects


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--departement", required=True, help="Ex: 35 ou 35,22,56")
    parser.add_argument("--metier", required=True, help="plombier, electricien, couvreur, paysagiste, menuisier ou 'tous'")
    parser.add_argument("--sortie", default="prospects.json")
    args = parser.parse_args()

    departements = args.departement.split(",")
    metiers = list(TAGS_PAR_METIER) if args.metier == "tous" else [args.metier]

    tous_prospects = []
    incomplets = 0
    avec_site = 0

    for dep in departements:
        for metier in metiers:
            if metier not in TAGS_PAR_METIER:
                print(f"Métier inconnu : {metier}")
                continue
            try:
                prospects = scraper_metier(dep, metier)
            except Exception as e:
                print(f"  Erreur sur {metier}/{dep} : {e}")
                continue

            for p in prospects:
                if p.pop("_site_existant", None):
                    avec_site += 1
                    continue  # a déjà un site, pas une cible
                if not p["email"]:
                    incomplets += 1
                if not p["telephone"] and not p["email"]:
                    continue  # ni tel ni mail = fiche inexploitable, on l'exclut
                tous_prospects.append(p)

            time.sleep(2)  # on ne matraque pas le serveur public gratuit

    with open(args.sortie, "w", encoding="utf-8") as f:
        json.dump(tous_prospects, f, ensure_ascii=False, indent=2)

    print(f"\n{len(tous_prospects)} prospects exploitables -> {args.sortie}")
    print(f"{incomplets} sans email (tel seul, à compléter ou à appeler)")
    print(f"{avec_site} exclus (ont déjà un site)")
    print("\nCoût total : 0 €")


if __name__ == "__main__":
    main()
