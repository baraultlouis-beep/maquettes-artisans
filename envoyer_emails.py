#!/usr/bin/env python3
"""
Envoie les emails de prospection générés (output/*-email.html) aux artisans
listés dans prospects.json, via Gmail SMTP. Même principe que Hermes :
anti-doublons (un prospect n'est jamais recontacté deux fois), log des envois.

Variables d'environnement requises (secrets GitHub Actions) :
    GMAIL_ADRESSE   -> baraultlouis@gmail.com
    GMAIL_MDP_APP   -> mot de passe d'application Gmail (pas le mdp du compte)

Usage local (test) :
    export GMAIL_ADRESSE="baraultlouis@gmail.com"
    export GMAIL_MDP_APP="xxxx xxxx xxxx xxxx"
    python envoyer_emails.py prospects.json --limite 5 --test

    --test   : envoie uniquement à toi-même (GMAIL_ADRESSE), pour vérifier le rendu
    --limite : nombre max d'emails envoyés dans cette exécution (sécurité anti-flood)
"""

import argparse
import datetime
import json
import os
import smtplib
import sys
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from generer_maquettes import METIERS, GITHUB_PAGES_BASE_URL

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR
LOG_ENVOIS = BASE_DIR / "envois_deja_faits.json"
TEMPLATE_RELANCE = BASE_DIR / "relance_prospection.html"

SMTP_HOTE = "smtp.gmail.com"
SMTP_PORT = 587
NOM_EXPEDITEUR = "Studio Web Bretagne"
EMAIL_CONTACT_DEFAUT = "baraultlouis@gmail.com"


def slugify(texte: str) -> str:
    import re
    import unicodedata
    texte = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    texte = re.sub(r"[^a-zA-Z0-9]+", "-", texte).strip("-").lower()
    return texte or "prospect"


def charger_log() -> dict:
    if LOG_ENVOIS.exists():
        data = json.loads(LOG_ENVOIS.read_text(encoding="utf-8"))
        if isinstance(data, list):  # migration depuis l'ancien format (simple liste)
            aujourdhui = time.strftime("%Y-%m-%d")
            return {cle: {"date": aujourdhui, "relance_envoyee": False} for cle in data}
        return data
    return {}


def sauver_log(log: dict):
    LOG_ENVOIS.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")


def envoyer_un_email(smtp, adresse_expediteur, mdp_app, destinataire, sujet, html):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = sujet
    msg["From"] = f"{NOM_EXPEDITEUR} <{adresse_expediteur}>"
    msg["To"] = destinataire
    msg.attach(MIMEText(html, "html", "utf-8"))
    smtp.sendmail(adresse_expediteur, destinataire, msg.as_string())


def generer_html_relance(prospect: dict, slug: str) -> str:
    metier = prospect.get("metier", "plombier")
    config_metier = METIERS.get(metier, METIERS["plombier"])
    palette = config_metier["palette"]
    email_contact = prospect.get("email_contact", EMAIL_CONTACT_DEFAUT)
    nom_url = prospect["nom"].replace(" ", "%20")

    remplacements = {
        "{{ARTISAN_NOM}}": prospect["nom"],
        "{{ARTISAN_NOM_URL}}": nom_url,
        "{{URL_MAQUETTE}}": f"{GITHUB_PAGES_BASE_URL}/{slug}.html",
        "{{EMAIL_CONTACT}}": email_contact,
        "{{LIEN_DESINSCRIPTION}}": f"mailto:{email_contact}?subject=Desinscription",
        "{{COULEUR_PRIMAIRE}}": prospect.get("couleur_primaire", palette["primaire"]),
        "{{COULEUR_ACCENT}}": prospect.get("couleur_accent", palette["accent"]),
    }
    html = TEMPLATE_RELANCE.read_text(encoding="utf-8")
    for variable, valeur in remplacements.items():
        html = html.replace(variable, valeur)
    return html


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("prospects_json")
    parser.add_argument("--limite", type=int, default=10, help="Nombre max d'emails envoyés cette exécution")
    parser.add_argument("--test", action="store_true", help="Envoie tout à toi-même au lieu des vrais prospects")
    parser.add_argument("--pause", type=float, default=8.0, help="Secondes entre deux envois (évite le flag spam)")
    parser.add_argument("--relance", action="store_true", help="Envoie la relance (1 seule fois, après --delai-relance jours) au lieu du premier contact")
    parser.add_argument("--delai-relance", type=int, default=5, help="Jours d'attente avant relance (défaut : 5)")
    args = parser.parse_args()

    adresse = os.environ.get("GMAIL_ADRESSE")
    mdp_app = os.environ.get("GMAIL_MDP_APP")
    if not adresse or not mdp_app:
        print("ERREUR : variables d'environnement GMAIL_ADRESSE et GMAIL_MDP_APP requises.")
        sys.exit(1)

    prospects = {p["email"]: p for p in json.loads(Path(args.prospects_json).read_text(encoding="utf-8")) if p.get("email")}
    log = charger_log()
    aujourdhui = datetime.date.today()

    a_envoyer = []  # (prospect, cle, slug)

    if args.relance:
        for cle, info in log.items():
            if info.get("relance_envoyee"):
                continue
            prospect = prospects.get(cle)
            if not prospect:
                continue  # plus dans prospects.json (retiré depuis), on ne relance pas dans le doute
            date_contact = datetime.date.fromisoformat(info["date"])
            if (aujourdhui - date_contact).days < args.delai_relance:
                continue
            a_envoyer.append((prospect, cle, slugify(prospect["nom"])))
    else:
        for cle, prospect in prospects.items():
            if cle in log:
                continue  # déjà contacté au moins une fois (premier contact ou relance)
            a_envoyer.append((prospect, cle, slugify(prospect["nom"])))

    a_envoyer = a_envoyer[: args.limite]

    if not a_envoyer:
        msg = "Rien à relancer (personne éligible à ce délai)." if args.relance else "Rien à envoyer (tout a déjà été contacté)."
        print(msg)
        return

    mode = "RELANCE" if args.relance else "PREMIER CONTACT"
    print(f"[{mode}] {len(a_envoyer)} email(s) à envoyer sur cette exécution (limite : {args.limite})")
    if args.test:
        print(f"Mode TEST : tout part vers {adresse} au lieu des vrais destinataires")

    with smtplib.SMTP(SMTP_HOTE, SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(adresse, mdp_app)

        for prospect, cle, slug in a_envoyer:
            destinataire = adresse if args.test else prospect["email"]

            if args.relance:
                html = generer_html_relance(prospect, slug)
                sujet = f"{prospect['nom']} — petit rappel sur votre maquette"
            else:
                chemin_email = OUTPUT_DIR / f"{slug}-email.html"
                if not chemin_email.exists():
                    print(f"  SKIP {prospect['nom']} — {chemin_email.name} introuvable, lance generer_maquettes.py d'abord")
                    continue
                html = chemin_email.read_text(encoding="utf-8")
                sujet = f"{prospect['nom']} — voici à quoi pourrait ressembler votre site"

            try:
                envoyer_un_email(smtp, adresse, mdp_app, destinataire, sujet, html)
                print(f"  OK — {prospect['nom']} ({destinataire})")
                if not args.test:
                    if args.relance:
                        log[cle]["relance_envoyee"] = True
                    else:
                        log[cle] = {"date": aujourdhui.isoformat(), "relance_envoyee": False}
            except Exception as e:
                print(f"  ECHEC — {prospect['nom']} : {e}")

            time.sleep(args.pause)

    if not args.test:
        sauver_log(log)
        print(f"\nLog mis à jour : {LOG_ENVOIS.name} ({len(log)} prospects contactés au total)")
    else:
        print("\nMode test : rien n'a été marqué comme envoyé dans le log.")


if __name__ == "__main__":
    main()
