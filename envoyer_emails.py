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
import json
import os
import smtplib
import sys
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
LOG_ENVOIS = BASE_DIR / "envois_deja_faits.json"

SMTP_HOTE = "smtp.gmail.com"
SMTP_PORT = 587
NOM_EXPEDITEUR = "Studio Web Bretagne"


def slugify(texte: str) -> str:
    import re
    import unicodedata
    texte = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    texte = re.sub(r"[^a-zA-Z0-9]+", "-", texte).strip("-").lower()
    return texte or "prospect"


def charger_log() -> set:
    if LOG_ENVOIS.exists():
        return set(json.loads(LOG_ENVOIS.read_text(encoding="utf-8")))
    return set()


def sauver_log(deja_envoyes: set):
    LOG_ENVOIS.write_text(
        json.dumps(sorted(deja_envoyes), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def envoyer_un_email(smtp, adresse_expediteur, mdp_app, destinataire, sujet, html):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = sujet
    msg["From"] = f"{NOM_EXPEDITEUR} <{adresse_expediteur}>"
    msg["To"] = destinataire
    msg.attach(MIMEText(html, "html", "utf-8"))
    smtp.sendmail(adresse_expediteur, destinataire, msg.as_string())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("prospects_json")
    parser.add_argument("--limite", type=int, default=10, help="Nombre max d'emails envoyés cette exécution")
    parser.add_argument("--test", action="store_true", help="Envoie tout à toi-même au lieu des vrais prospects")
    parser.add_argument("--pause", type=float, default=8.0, help="Secondes entre deux envois (évite le flag spam)")
    args = parser.parse_args()

    adresse = os.environ.get("GMAIL_ADRESSE")
    mdp_app = os.environ.get("GMAIL_MDP_APP")
    if not adresse or not mdp_app:
        print("ERREUR : variables d'environnement GMAIL_ADRESSE et GMAIL_MDP_APP requises.")
        sys.exit(1)

    prospects = json.loads(Path(args.prospects_json).read_text(encoding="utf-8"))
    deja_envoyes = charger_log()

    a_envoyer = []
    for p in prospects:
        cle = p["email"] or f"tel:{p['telephone']}"
        if not p.get("email"):
            continue  # pas d'email = pas d'envoi possible, à traiter par téléphone à part
        if cle in deja_envoyes:
            continue
        a_envoyer.append((p, cle))

    a_envoyer = a_envoyer[: args.limite]

    if not a_envoyer:
        print("Rien à envoyer (tout a déjà été contacté, ou aucun email valide).")
        return

    print(f"{len(a_envoyer)} email(s) à envoyer sur cette exécution (limite : {args.limite})")
    if args.test:
        print(f"Mode TEST : tout part vers {adresse} au lieu des vrais destinataires")

    with smtplib.SMTP(SMTP_HOTE, SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(adresse, mdp_app)

        for prospect, cle in a_envoyer:
            slug = slugify(prospect["nom"])
            chemin_email = OUTPUT_DIR / f"{slug}-email.html"
            if not chemin_email.exists():
                print(f"  SKIP {prospect['nom']} — {chemin_email.name} introuvable, lance generer_maquettes.py d'abord")
                continue

            html = chemin_email.read_text(encoding="utf-8")
            destinataire = adresse if args.test else prospect["email"]
            sujet = f"{prospect['nom']} — voici à quoi pourrait ressembler votre site"

            try:
                envoyer_un_email(smtp, adresse, mdp_app, destinataire, sujet, html)
                print(f"  OK — {prospect['nom']} ({destinataire})")
                if not args.test:
                    deja_envoyes.add(cle)
            except Exception as e:
                print(f"  ECHEC — {prospect['nom']} : {e}")

            time.sleep(args.pause)

    if not args.test:
        sauver_log(deja_envoyes)
        print(f"\nLog mis à jour : {LOG_ENVOIS.name} ({len(deja_envoyes)} prospects contactés au total)")
    else:
        print("\nMode test : rien n'a été marqué comme envoyé dans le log.")


if __name__ == "__main__":
    main()
