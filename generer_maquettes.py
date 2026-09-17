#!/usr/bin/env python3
"""
Génère une maquette HTML personnalisée par prospect, à partir d'un template
métier et d'une liste de prospects (JSON). Aucun appel API payant : simple
remplacement de variables. Coût par prospect = 0.

Usage :
    python generer_maquettes.py prospects.json

Structure attendue de prospects.json : une liste d'objets, un par artisan.
Voir prospects_exemple.json pour un exemple complet.

Champs obligatoires : nom, ville, telephone, email, metier
Champs optionnels   : zone_intervention, annees_experience, accroche_perso,
                       description_courte, communes (liste)

Si un champ optionnel est absent, une valeur par défaut cohérente est
générée automatiquement (aucun {{VARIABLE}} ne doit rester dans le HTML final).
"""

import json
import re
import sys
import unicodedata
from pathlib import Path

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR
OUTPUT_DIR = BASE_DIR

# Un template HTML par métier. Ajouter une entrée ici dès qu'un nouveau
# template est créé (électricien, couvreur, paysagiste, menuisier...).
TEMPLATE_SITE = "artisan-template.html"
TEMPLATE_EMAIL = "email_prospection.html"

# À adapter une fois le dépôt GitHub Pages créé, ex :
# "https://tonpseudo.github.io/maquettes-artisans"
GITHUB_PAGES_BASE_URL = "https://baraultlouis-beep.github.io/maquettes-artisans"

EMAIL_CONTACT_DEFAUT = "baraultlouis@gmail.com"
LIEN_DESINSCRIPTION_DEFAUT = f"mailto:{EMAIL_CONTACT_DEFAUT}?subject=Desinscription"

# Icônes réutilisables (juste le contenu interne du <svg>, viewBox 0 0 24 24)
ICONS = {
    "wrench":  '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.1 2.1a2 2 0 0 1-2.8-2.8z"/>',
    "sink":    '<path d="M4 12h16M4 12a4 4 0 0 1 4-4h8a4 4 0 0 1 4 4M4 12v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/><circle cx="8" cy="8" r="1.4" style="fill:var(--copper)" stroke="none"/>',
    "flame":   '<path d="M12 2c2 3-1 4-1 6a3 3 0 1 0 6 0c0-1-.5-2-1-2.5.5 2.5-1 3.5-2 2 1-1 .5-3-2-5.5zM6 14a6 6 0 1 0 12 0c0-2-1-3.5-2.5-5"/>',
    "restore": '<path d="M3 21l6-6M13.5 10.5L21 3l-3 1-1 3-7.5 7.5a2.1 2.1 0 1 0 3 3z"/>',
    "bolt":    '<path d="M13 2 4 14h7l-1 8 9-12h-7l1-8z" stroke-linejoin="round"/>',
    "shield":  '<path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3z"/><path d="M9 12l2 2 4-4"/>',
    "panel":   '<rect x="5" y="4" width="14" height="16" rx="1.5"/><path d="M9 8h6M9 12h6M9 16h3"/>',
    "roof":    '<path d="M3 12 12 4l9 8"/><path d="M6 11v8h12v-8"/><path d="M10 19v-5h4v5"/>',
    "layers":  '<path d="M12 3 3 8l9 5 9-5-9-5z"/><path d="M3 13l9 5 9-5"/>',
    "drop":    '<path d="M12 3s7 7.5 7 12.5A7 7 0 0 1 5 15.5C5 10.5 12 3 12 3z"/>',
    "leaf":    '<path d="M4 20C4 10 12 4 20 4c0 8-6 16-16 16z"/><path d="M4 20c3-6 8-10 14-13"/>',
    "scissors":'<circle cx="6" cy="6" r="2.5"/><circle cx="6" cy="18" r="2.5"/><path d="M8.5 7.5 20 19M8.5 16.5 20 5"/>',
    "tree":    '<path d="M12 3 7 11h3l-4 7h4v3h4v-3h4l-4-7h3z"/>',
    "ruler":   '<path d="M3 16 16 3l5 5L8 21l-5-5z"/><path d="M7.5 12.5l2 2M11 9l2 2M14.5 5.5l2 2"/>',
    "window":  '<rect x="4" y="4" width="16" height="16" rx="1.5"/><path d="M12 4v16M4 12h16"/>',
    "shelf":   '<path d="M4 4h16v6H4zM4 14h16v6H4z"/><path d="M8 4v6M8 14v6"/>',
}


def icone(nom: str) -> str:
    return (
        '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" '
        'style="stroke:var(--copper)" stroke-width="1.8" stroke-linecap="round">'
        f'{ICONS[nom]}</svg>'
    )


# Motif central du hero (remplace le simple pictogramme "clé + tuyau" du plombier
# par une composition adaptée à chaque métier). Les cercles de fond restent fixes.
HERO_MARKS = {
    "plombier": '''
        <path d="M70 210 L70 140 Q70 120 90 120 L190 120 Q210 120 210 100 L210 70"
              style="stroke:var(--copper-soft)" stroke-width="3" fill="none" stroke-linecap="round"/>
        <circle cx="70" cy="210" r="9" style="fill:var(--copper)"/>
        <circle cx="210" cy="70" r="9" style="fill:var(--copper)"/>
        <g transform="translate(150,175) rotate(-28)">
          <rect x="-11" y="-58" width="22" height="86" rx="10" style="fill:var(--bg)"/>
          <path d="M-24 -58 a24 24 0 0 1 48 0 v14 a24 24 0 0 1 -48 0 z" style="fill:var(--bg)"/>
          <circle cx="0" cy="-58" r="10" style="fill:var(--petrol)"/>
        </g>
        <path d="M226 190 q10 14 0 26 q-10 -12 0 -26 z" style="fill:var(--copper-soft)" opacity="0.85"/>
        <path d="M248 220 q8 11 0 21 q-8 -10 0 -21 z" style="fill:var(--copper-soft)" opacity="0.55"/>''',
    "electricien": '''
        <path d="M172 90 100 190h50l-14 60 82-100h-52z"
              style="fill:var(--copper)" stroke="none"/>
        <circle cx="90" cy="150" r="4" style="fill:var(--copper-soft)"/>
        <circle cx="230" cy="110" r="4" style="fill:var(--copper-soft)"/>
        <circle cx="220" cy="220" r="4" style="fill:var(--copper-soft)"/>''',
    "couvreur": '''
        <path d="M80 190 160 110 240 190" style="stroke:var(--copper-soft)" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M100 185v55h120v-55" style="stroke:var(--copper-soft)" stroke-width="3" fill="none"/>
        <path d="M140 240v-35h40v35" style="stroke:var(--copper)" stroke-width="3" fill="none"/>
        <path d="M70 195 160 100 250 195" style="stroke:var(--copper)" stroke-width="4" fill="none" stroke-linecap="round" stroke-linejoin="round"/>''',
    "paysagiste": '''
        <path d="M160 230V150" style="stroke:var(--copper)" stroke-width="4" stroke-linecap="round"/>
        <path d="M160 150c-40 0-60-30-60-60 40 0 60 30 60 60z" style="fill:var(--copper-soft)"/>
        <path d="M160 170c35 0 52-26 52-52-35 0-52 26-52 52z" style="fill:var(--copper-soft)" opacity="0.75"/>
        <path d="M120 230h80" style="stroke:var(--copper-soft)" stroke-width="3" stroke-linecap="round"/>''',
    "menuisier": '''
        <rect x="90" y="90" width="140" height="140" rx="6" style="stroke:var(--copper-soft)" stroke-width="3" fill="none"/>
        <path d="M90 90 230 230M230 90 90 230" style="stroke:var(--copper-soft)" stroke-width="1.5" opacity="0.5"/>
        <rect x="130" y="130" width="60" height="60" rx="4" style="fill:var(--copper)"/>''',
}

# Palette + textes + prestations + réalisations par métier
METIERS = {
    "plombier": {
        "titre": "Plombier", "domaine": "plomberie",
        "palette": {"primaire": "#14262B", "primaire_claire": "#1F3B3D", "accent": "#B6702F", "accent_claire": "#E7D3BE"},
        "services": [
            ("Dépannage urgent", "Fuite, canalisation bouchée, chauffe-eau en panne : intervention rapide pour limiter les dégâts, 7j/7 sur les urgences.", "wrench"),
            ("Installation sanitaire", "Salle de bain, cuisine, robinetterie : installation complète ou remplacement d'équipements, avec des matériaux durables.", "sink"),
            ("Chauffage et eau chaude", "Pose et entretien de chaudières, ballons d'eau chaude et systèmes de chauffage adaptés à votre logement.", "flame"),
            ("Rénovation de plomberie", "Remise aux normes d'une installation ancienne, refonte de réseau : un diagnostic clair avant chaque chantier.", "restore"),
        ],
        "realisations": ["Rénovation de salle de bain", "Dépannage fuite d'urgence", "Installation chauffe-eau"],
    },
    "electricien": {
        "titre": "Électricien", "domaine": "électricité",
        "palette": {"primaire": "#1A1F3D", "primaire_claire": "#272D52", "accent": "#D9A441", "accent_claire": "#EFE0BC"},
        "services": [
            ("Dépannage électrique urgent", "Panne, coupure, disjoncteur qui saute : intervention rapide pour rétablir votre installation en sécurité.", "bolt"),
            ("Mise aux normes", "Tableau électrique, prises, câblage : mise en conformité de votre installation selon les normes en vigueur.", "shield"),
            ("Tableau et domotique", "Installation ou remplacement de tableau électrique, ajout de solutions domotiques adaptées à votre logement.", "panel"),
            ("Rénovation électrique", "Refonte complète d'une installation ancienne, avec un diagnostic clair avant chaque chantier.", "restore"),
        ],
        "realisations": ["Mise aux normes tableau électrique", "Dépannage panne totale", "Installation domotique"],
    },
    "couvreur": {
        "titre": "Couvreur", "domaine": "couverture",
        "palette": {"primaire": "#2B2622", "primaire_claire": "#3D3630", "accent": "#B4502E", "accent_claire": "#E9CDBE"},
        "services": [
            ("Réparation de toiture urgente", "Fuite, tuiles endommagées, dégât des eaux : intervention rapide pour protéger votre logement.", "roof"),
            ("Rénovation de couverture", "Remplacement complet ou partiel de toiture, avec des matériaux adaptés à votre région.", "layers"),
            ("Isolation combles et toiture", "Isolation thermique de la toiture pour réduire vos déperditions de chaleur toute l'année.", "shield"),
            ("Zinguerie et gouttières", "Pose et entretien de gouttières, chéneaux et évacuations d'eaux pluviales.", "drop"),
        ],
        "realisations": ["Réfection complète de toiture", "Réparation fuite après tempête", "Pose de gouttières"],
    },
    "paysagiste": {
        "titre": "Paysagiste", "domaine": "paysagisme",
        "palette": {"primaire": "#1E2E22", "primaire_claire": "#2C4231", "accent": "#8A7A3A", "accent_claire": "#E3DDC0"},
        "services": [
            ("Entretien de jardin", "Tonte, désherbage, entretien régulier : un jardin impeccable toute l'année sans y penser.", "leaf"),
            ("Création d'espaces verts", "Conception et plantation d'un jardin sur mesure, adapté à votre terrain et à vos envies.", "tree"),
            ("Élagage et taille", "Taille de haies, élagage d'arbres : un travail soigné pour la sécurité et l'esthétique de votre extérieur.", "scissors"),
            ("Aménagement extérieur", "Terrasse, allée, clôture : des aménagements durables pour profiter pleinement de votre jardin.", "layers"),
        ],
        "realisations": ["Création de jardin paysager", "Taille de haie et élagage", "Aménagement de terrasse"],
    },
    "menuisier": {
        "titre": "Menuisier", "domaine": "menuiserie",
        "palette": {"primaire": "#2E2016", "primaire_claire": "#42301F", "accent": "#B08B4F", "accent_claire": "#E9DCC3"},
        "services": [
            ("Menuiserie sur mesure", "Meubles, escaliers, aménagements : des pièces sur mesure pensées pour votre intérieur.", "ruler"),
            ("Pose de fenêtres et portes", "Remplacement ou installation de menuiseries extérieures, pour plus de confort et d'isolation.", "window"),
            ("Agencement intérieur", "Placards, dressings, bibliothèques : des rangements sur mesure qui s'intègrent parfaitement.", "shelf"),
            ("Rénovation de menuiserie", "Restauration de menuiseries anciennes avec un diagnostic clair avant chaque chantier.", "restore"),
        ],
        "realisations": ["Dressing sur mesure", "Pose de fenêtres double vitrage", "Restauration escalier ancien"],
    },
}


def slugify(texte: str) -> str:
    """Transforme 'Dupont Plomberie' en 'dupont-plomberie' pour le nom de fichier."""
    texte = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    texte = re.sub(r"[^a-zA-Z0-9]+", "-", texte).strip("-").lower()
    return texte or "prospect"


def telephone_lien(telephone: str) -> str:
    """'02 99 12 34 56' -> '+33299123456' pour le lien tel:"""
    chiffres = re.sub(r"\D", "", telephone)
    if chiffres.startswith("0"):
        chiffres = "33" + chiffres[1:]
    return "+" + chiffres


def valeurs_par_defaut(prospect: dict) -> dict:
    """Complète les champs optionnels manquants avec des valeurs raisonnables."""
    nom = prospect["nom"]
    ville = prospect["ville"]
    metier = prospect.get("metier", "plombier")
    config_metier = METIERS.get(metier, METIERS["plombier"])
    domaine = config_metier["domaine"]

    defauts = {
        "annees_experience": "10",
        "accroche_perso": f"{nom}, votre {metier} de confiance à {ville}",
        "description_courte": (
            f"Intervention rapide, devis gratuit et travail soigné : "
            f"{nom} accompagne les habitants de {ville} et des environs "
            f"pour tous leurs besoins en {domaine}."
        ),
        "zone_intervention": f"{ville} et un rayon de 20 km",
        "communes": [ville],
        "histoire": (
            f"{nom} intervient depuis {prospect.get('annees_experience', 10)} ans "
            f"auprès des particuliers et professionnels de {ville}. Une entreprise "
            f"à taille humaine, où chaque chantier est suivi directement par "
            f"l'artisan, du premier contact jusqu'à la fin des travaux."
        ),
        "realisations_liste": METIERS.get(metier, METIERS["plombier"])["realisations"],
    }
    fusion = {**defauts, **prospect}
    return fusion


def bloc_services(services: list) -> str:
    """Génère les lignes de prestations avec leur icône, à partir de la config du métier."""
    html = []
    for titre, description, icone_nom in services:
        html.append(f"""
    <div class="service-row">
      <div class="service-icon">{icone(icone_nom)}</div>
      <div>
        <h3>{titre}</h3>
        <p>{description}</p>
      </div>
    </div>""")
    return "".join(html)


def bloc_realisations(items: list) -> str:
    """Génère la grille de 'types de chantiers' (catégories, pas de faux exemples précis)."""
    html = []
    for i, item in enumerate(items, start=1):
        html.append(f"""
        <div class="realisation-item">
          <span class="num">{i:02d}</span>
          <h3>{item}</h3>
          <p>Réalisé sur mesure selon la configuration du logement.</p>
        </div>""")
    return "".join(html)


def bloc_avis() -> str:
    """
    Emplacement 'avis' générique en attendant la connexion aux vrais avis Google
    de l'artisan (une fois le client validé) — pas d'avis fictif attribué à une
    personne inventée.
    """
    return """
    <div class="avis-item">
      <div class="avis-stars">★★★★★</div>
      <p>Emplacement réservé aux avis Google de l'établissement, à connecter une fois le site validé.</p>
      <div class="avis-note">Avis clients vérifiés</div>
    </div>
    <div class="avis-item">
      <div class="avis-stars">★★★★★</div>
      <p>Vos avis existants (Google, Facebook, Pages Jaunes) peuvent être repris ici tels quels.</p>
      <div class="avis-note">Sur simple validation de votre part</div>
    </div>"""


def generer_maquette(prospect: dict) -> str:
    prospect = valeurs_par_defaut(prospect)
    metier = prospect.get("metier", "plombier")
    config_metier = METIERS.get(metier)
    if not config_metier:
        raise ValueError(f"Métier '{metier}' inconnu. Métiers disponibles : {list(METIERS)}")

    html = (TEMPLATES_DIR / TEMPLATE_SITE).read_text(encoding="utf-8")

    palette_defaut = config_metier["palette"]
    couleur_primaire = prospect.get("couleur_primaire", palette_defaut["primaire"])
    couleur_accent = prospect.get("couleur_accent", palette_defaut["accent"])
    # Les variantes claires suivent la surcharge si fournie, sinon la palette du métier
    couleur_primaire_claire = prospect.get("couleur_primaire_claire", palette_defaut["primaire_claire"])
    couleur_accent_claire = prospect.get("couleur_accent_claire", palette_defaut["accent_claire"])

    communes_html = "".join(f"<span>{c}</span>" for c in prospect["communes"])

    remplacements = {
        "{{ARTISAN_NOM}}": prospect["nom"],
        "{{VILLE}}": prospect["ville"],
        "{{TELEPHONE}}": prospect["telephone"],
        "{{TELEPHONE_LIEN}}": telephone_lien(prospect["telephone"]),
        "{{EMAIL}}": prospect["email"],
        "{{METIER_TITRE}}": config_metier["titre"],
        "{{METIER_MIN}}": config_metier["titre"].lower(),
        "{{DOMAINE}}": config_metier["domaine"],
        "{{ZONE_INTERVENTION}}": prospect["zone_intervention"],
        "{{ANNEES_EXPERIENCE}}": str(prospect["annees_experience"]),
        "{{ACCROCHE_PERSO}}": prospect["accroche_perso"],
        "{{DESCRIPTION_COURTE}}": prospect["description_courte"],
        "{{LISTE_COMMUNES}}": communes_html,
        "{{HISTOIRE}}": prospect["histoire"],
        "{{SERVICES}}": bloc_services(config_metier["services"]),
        "{{REALISATIONS}}": bloc_realisations(prospect["realisations_liste"]),
        "{{AVIS}}": bloc_avis(),
        "{{HERO_MARK}}": HERO_MARKS.get(metier, HERO_MARKS["plombier"]),
        "{{COULEUR_PRIMAIRE}}": couleur_primaire,
        "{{COULEUR_PRIMAIRE_CLAIRE}}": couleur_primaire_claire,
        "{{COULEUR_ACCENT}}": couleur_accent,
        "{{COULEUR_ACCENT_CLAIRE}}": couleur_accent_claire,
    }

    for variable, valeur in remplacements.items():
        html = html.replace(variable, valeur)

    restants = re.findall(r"{{[A-Z_]+}}", html)
    if restants:
        print(f"  ATTENTION — variables non remplacées pour {prospect['nom']} : {restants}")

    return html


def generer_email(prospect: dict, slug: str) -> str:
    prospect = valeurs_par_defaut(prospect)
    metier = prospect.get("metier", "plombier")
    config_metier = METIERS.get(metier, METIERS["plombier"])
    html = (TEMPLATES_DIR / TEMPLATE_EMAIL).read_text(encoding="utf-8")

    palette_defaut = config_metier["palette"]
    couleur_primaire = prospect.get("couleur_primaire", palette_defaut["primaire"])
    couleur_accent = prospect.get("couleur_accent", palette_defaut["accent"])
    couleur_accent_claire = prospect.get("couleur_accent_claire", palette_defaut["accent_claire"])

    url_maquette = f"{GITHUB_PAGES_BASE_URL}/{slug}.html"
    nom_url = prospect["nom"].replace(" ", "%20")
    email_contact = prospect.get("email_contact", EMAIL_CONTACT_DEFAUT)

    remplacements = {
        "{{ARTISAN_NOM}}": prospect["nom"],
        "{{ARTISAN_NOM_URL}}": nom_url,
        "{{VILLE}}": prospect["ville"],
        "{{METIER}}": config_metier["titre"].lower(),
        "{{METIER_MAJ}}": config_metier["titre"],
        "{{TELEPHONE}}": prospect["telephone"],
        "{{ACCROCHE_PERSO}}": prospect["accroche_perso"],
        "{{URL_MAQUETTE}}": url_maquette,
        "{{EMAIL_CONTACT}}": email_contact,
        "{{PRENOM_CONTACT}}": prospect.get("prenom_contact", "Louis"),
        "{{LIEN_DESINSCRIPTION}}": f"mailto:{email_contact}?subject=Desinscription",
        "{{COULEUR_PRIMAIRE}}": couleur_primaire,
        "{{COULEUR_ACCENT}}": couleur_accent,
        "{{COULEUR_ACCENT_CLAIRE}}": couleur_accent_claire,
    }
    for variable, valeur in remplacements.items():
        html = html.replace(variable, valeur)

    restants = re.findall(r"{{[A-Z_]+}}", html)
    if restants:
        print(f"  ATTENTION — variables non remplacées (email) pour {prospect['nom']} : {restants}")

    return html


def main():
    if len(sys.argv) != 2:
        print("Usage : python generer_maquettes.py prospects.json")
        sys.exit(1)

    fichier_prospects = Path(sys.argv[1])
    prospects = json.loads(fichier_prospects.read_text(encoding="utf-8"))

    OUTPUT_DIR.mkdir(exist_ok=True)

    for prospect in prospects:
        slug = slugify(prospect["nom"])

        html_site = generer_maquette(prospect)
        (OUTPUT_DIR / f"{slug}.html").write_text(html_site, encoding="utf-8")

        html_email = generer_email(prospect, slug)
        (OUTPUT_DIR / f"{slug}-email.html").write_text(html_email, encoding="utf-8")

        print(f"OK — {prospect['nom']} -> {slug}.html + {slug}-email.html")

    print(f"\n{len(prospects)} maquette(s) + email(s) généré(s) dans {OUTPUT_DIR}/")
    print("Coût total : 0 € (aucun appel API)")
    print(f"\nPense à remplacer GITHUB_PAGES_BASE_URL ({GITHUB_PAGES_BASE_URL}) une fois ton dépôt créé.")


if __name__ == "__main__":
    main()
