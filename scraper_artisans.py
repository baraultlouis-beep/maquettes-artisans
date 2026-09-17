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
from pathlib import Path

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Tag OSM correspondant à chaque métier (shop=* ou craft=*)
TAGS_PAR_METIER = {
    "plombier": ['"craft"="plumber"'],
    "electricien": ['"craft"="electrician"'],
    "couvreur": ['"craft"="roofer"'],
    "paysagiste": ['"shop"="garden_centre"', '"craft"="gardener"'],
    "menuisier": ['"craft"="carpenter"'],
}

# Codes des départements de France métropolitaine (pour le mode --departement national)
DEPARTEMENTS_FRANCE_METRO = [f"{i:02d}" for i in range(1, 96) if i != 20] + ["2A", "2B"]


def construire_requete(departement: str, tags: list) -> str:
    # Sélection du département par son code INSEE (ref:INSEE) : marche pour
    # n'importe quel département français, pas besoin de connaître son nom.
    filtres = "".join(f'  node[{tag}](area.zone);\n  way[{tag}](area.zone);\n' for tag in tags)
    return f"""
[out:json][timeout:60];
area["boundary"="administrative"]["admin_level"="6"]["ref:INSEE"="{departement}"]->.zone;
(
{filtres}
);
out center tags;
"""


def interroger_overpass(requete: str) -> dict:
    data = requete.encode("utf-8")
    headers = {
        "User-Agent": "ScraperArtisans/1.0 (usage personnel, contact: baraultlouis@gmail.com)",
        "Content-Type": "text/plain; charset=utf-8",
    }
    req = urllib.request.Request(OVERPASS_URL, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=90) as reponse:
        return json.loads(reponse.read().decode("utf-8"))


def extraire_prospect(element: dict, metier: str) -> dict | None:
    tags = element.get("tags", {})
    nom = tags.get("name")
    if not nom:
        return None  # on ignore les fiches sans nom, inutilisables pour un mail personnalisé

    ville = tags.get("addr:city") or tags.get("addr:town") or tags.get("addr:suburb") or tags.get("addr:village") or ""
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


def charger_existant(fichier_sortie: str) -> list:
    """Recharge ce qui a déjà été scrapé lors d'exécutions précédentes (les 3 fichiers),
    pour fusionner au lieu d'écraser quand on relance sur d'autres métiers/départements."""
    tous = []
    for fichier, sans_ville in [
        (fichier_sortie, False),
        ("a_verifier_manuellement.json", False),
        ("sans_ville_a_completer.json", True),
    ]:
        chemin = Path(fichier)
        if not chemin.exists():
            continue
        for p in json.loads(chemin.read_text(encoding="utf-8")):
            if sans_ville:
                p["_sans_ville"] = True
            tous.append(p)
    return tous


DEPTS_FAITS_FICHIER = Path("departements_scrapes.json")


def charger_depts_faits() -> set:
    if DEPTS_FAITS_FICHIER.exists():
        return set(json.loads(DEPTS_FAITS_FICHIER.read_text(encoding="utf-8")))
    return set()


def marquer_dept_fait(depts_faits: set, metier: str, dep: str):
    depts_faits.add(f"{metier}:{dep}")
    DEPTS_FAITS_FICHIER.write_text(json.dumps(sorted(depts_faits), ensure_ascii=False, indent=2), encoding="utf-8")


def cle_dedoublonnage(p: dict) -> tuple:
    return (p.get("nom", "").strip().lower(), p.get("telephone", "").strip())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--departement", required=True, help="Ex: 35 ou 35,22,56 ou 'national' pour toute la France")
    parser.add_argument("--metier", required=True, help="plombier, electricien, couvreur, paysagiste, menuisier ou 'tous'")
    parser.add_argument("--sortie", default="prospects.json")
    args = parser.parse_args()

    if args.departement == "national":
        departements = DEPARTEMENTS_FRANCE_METRO
        print(f"Mode national : {len(departements)} départements — ça va prendre du temps (comptez ~5-10s par département), pause de sécurité entre chaque requête.")
    else:
        departements = args.departement.split(",")
    metiers = list(TAGS_PAR_METIER) if args.metier == "tous" else args.metier.split(",")

    tous_prospects = charger_existant(args.sortie)
    deja_vus = {cle_dedoublonnage(p) for p in tous_prospects}
    depts_faits = charger_depts_faits()
    if tous_prospects:
        print(f"Fusion avec {len(tous_prospects)} prospect(s) déjà scrapés précédemment (pas de doublon, pas de perte).")
    if depts_faits:
        print(f"{len(depts_faits)} combinaison(s) département/métier déjà faites, seront sautées.")
    incomplets = 0
    echecs_consecutifs = 0

    for dep in departements:
        for metier in metiers:
            if metier not in TAGS_PAR_METIER:
                print(f"Métier inconnu : {metier}")
                continue
            if f"{metier}:{dep}" in depts_faits:
                print(f"  (dept {dep} déjà fait, sauté)")
                continue  # déjà scrapé avec succès lors d'une session précédente
            try:
                prospects = scraper_metier(dep, metier)
                echecs_consecutifs = 0  # une requête a marché, on repart de zéro
                marquer_dept_fait(depts_faits, metier, dep)
            except Exception as e:
                echecs_consecutifs += 1
                print(f"  Erreur sur {metier}/{dep} : {e} (échec n°{echecs_consecutifs} d'affilée)")

                if echecs_consecutifs >= 5:
                    print(
                        f"\nARRÊT — 5 échecs d'affilée. Ce qui a déjà été trouvé est sauvegardé. "
                        f"Vérifie le message d'erreur ci-dessus : si c'est 'Not Acceptable' ou une "
                        f"erreur réseau, relance dans 15-20 min ; si l'erreur persiste après ça, "
                        f"montre-moi le message exact."
                    )
                    ecrire_sorties(tous_prospects, args.sortie)
                    return
                continue

            for p in prospects:
                site = p.pop("_site_existant", None)
                if not p["telephone"] and not p["email"]:
                    continue  # ni tel ni mail = fiche inexploitable, on l'exclut
                cle = cle_dedoublonnage(p)
                if cle in deja_vus:
                    continue  # déjà trouvé lors d'un passage précédent (autre métier/session)
                deja_vus.add(cle)
                if not p["ville"]:
                    p["_sans_ville"] = True  # ville introuvable : mail personnalisé cassé sinon, on l'écarte du lot prêt à envoyer
                if site:
                    p["site_existant"] = site
                if not site and not p["email"] and p["ville"]:
                    incomplets += 1
                tous_prospects.append(p)

            # sauvegarde après CHAQUE département : si tu coupes le script en
            # cours de route, rien n'est perdu de ce qui a déjà été trouvé.
            ecrire_sorties(tous_prospects, args.sortie)

            time.sleep(3)  # pause de sécurité, on ne matraque pas le serveur public gratuit

    prets = len([p for p in tous_prospects if not p.get("site_existant") and not p.get("_sans_ville")])
    avec_site = len([p for p in tous_prospects if p.get("site_existant") and not p.get("_sans_ville")])
    sans_ville = len([p for p in tous_prospects if p.get("_sans_ville")])
    print(f"\nTerminé — {prets} prospects prêts à envoyer -> {args.sortie}")
    print(f"{incomplets} d'entre eux sans email (tel seul, à compléter ou à appeler)")
    print(f"{avec_site} prospects AVEC un site existant -> a_verifier_manuellement.json")
    print(f"{sans_ville} prospects sans ville trouvable -> sans_ville_a_completer.json (à compléter à la main si tu veux les récupérer)")
    print("\nCoût total : 0 €")


def ecrire_sorties(tous_prospects: list, fichier_sortie: str):
    sans_ville = [p for p in tous_prospects if p.get("_sans_ville")]
    avec_site = [p for p in tous_prospects if p.get("site_existant") and not p.get("_sans_ville")]
    prets = [
        {k: v for k, v in p.items() if k not in ("_sans_ville",)}
        for p in tous_prospects
        if not p.get("site_existant") and not p.get("_sans_ville")
    ]
    with open(fichier_sortie, "w", encoding="utf-8") as f:
        json.dump(prets, f, ensure_ascii=False, indent=2)
    with open("a_verifier_manuellement.json", "w", encoding="utf-8") as f:
        json.dump(avec_site, f, ensure_ascii=False, indent=2)
    with open("sans_ville_a_completer.json", "w", encoding="utf-8") as f:
        json.dump([{k: v for k, v in p.items() if k != "_sans_ville"} for p in sans_ville], f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
