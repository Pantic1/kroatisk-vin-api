"""Fylder emballage-stamdata med flaskevægtene fra kvartalsregnearket.

Varenumrene stammer fra Galićs pakirna lista (kolonnen efter Rbr./No.).
Vægten afhænger af flasken, ikke af årgangen, så navnene står uden årstal.

Kør:  venv/bin/python -m scripts.seed_packaging_materials
Scriptet kan køres igen – eksisterende varer opdateres, der oprettes ikke dubletter.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.config import engine, sessionLocal          # noqa: E402
from config.model import (Base, PackagingInvoice,        # noqa: E402
                          PackagingLine, PackagingMaterial,
                          PackagingOutbound)

# (varenr, navn, kg tom flaske, flaskestørrelse, ekstra søgeord)
MATERIALS = [
    ("0108", "Graševina 0,75L",             0.616, "0,75 L", "GRAŠEVINA 0,75l"),
    ("0109", "Sauvignon 0,75L",             0.611, "0,75 L", "SAUVIGNON 0,75l;Sauvignon Blanc"),
    ("0149", "Chardonnay 0,75L",            0.706, "0,75 L", "CHARDONNAY 0,75L"),
    ("0028", "Graševina Kasna Berba 0,75L", 0.616, "0,75 L", "GRAŠEVINA KASNA BERBA;Grasevina kasna berba"),
    ("0060", "Bijelo 9 0,75L",              0.606, "0,75 L", "BIJELO 9"),
    ("0110", "Rosé 0,75L",                  0.615, "0,75 L", "ROSE 0,75l;Rose"),
    ("0103", "Cuvée 6 0,75L",               0.620, "0,75 L", "CUVEE 6;Cuvee 6"),
    ("0095", "Pinot Crni 0,75L",            0.702, "0,75 L", "PINOT CRNI"),
    ("0044", "Crno 9 0,75L",                0.612, "0,75 L", "CRNO 9"),
    ("1016", "Graševina Mateo 0,375L",      0.538, "0,375 L", "GRAŠEVINA MATEO;Galic Mateo"),
    ("0093", "Le Clos 0,75L",               0.744, "0,75 L", "LE CLOS"),
    ("0055", "Code Rosé 0,75L",             0.902, "0,75 L", "CODE ROSE"),
    ("0056", "Code White 0,75L",            0.902, "0,75 L", "CODE WHITE"),
    ("0057", "Code Black 0,75L",            0.920, "0,75 L", "CODE BLACK"),
    ("0003", "G Točka Crna 0,75L",          0.902, "0,75 L", "G TOČKA CRNA;G Točka Crno;G Tocka Crno"),
    ("0107", "G Točka Bijela 0,75L",        0.453, "0,75 L", "G TOČKA BIJELA;G Tocka Bijela"),
    ("0079", "Pošip Ego 0,75L",             0.702, "0,75 L", "POŠIP EGO;Ego Pošip;Ego Posip"),
    ("0034", "Ego Babić 0,75L",             0.702, "0,75 L", "EGO BABIĆ;Ego Babic"),
    ("0035", "Ego Tribidrag 0,75L",         0.702, "0,75 L", "EGO TRIBIDRAG"),
    ("0096", "Ego Plavac Mali 0,75L",       0.702, "0,75 L", "EGO PLAVAC MALI"),
    ("0140", "Ego Bubble M 0,75L",          0.902, "0,75 L", "Ego - Bubble M;EGO BUBBLE M"),
    ("0142", "Ego Bubble B 0,75L",          0.902, "0,75 L", "EGO - Bubble B;EGO BUBBLE B"),
    # Står i regnearket, men optræder ikke på den følgeseddel vi har set –
    # varenummeret udfyldes første gang de kommer med en levering.
    (None,   "Macerator 0,75L",             0.710, "0,75 L", "MACERATOR;Macerator Orange Wine"),
    (None,   "Rosé Magnum 1,5L",            1.303, "1,5 L",  "ROSE MAGNUM;Rosé Magnum"),
]

CARTON_KG = 0.0648   # pap pr. flaske – ens for alle varer i regnearket


def main():
    # Opretter de emballage-tabeller der mangler. API'et gør det ikke selv:
    # det kører serverless, og et create_all ved hver kold start koster
    # unødige databasekald.
    Base.metadata.create_all(bind=engine, tables=[
        PackagingMaterial.__table__,
        PackagingInvoice.__table__,
        PackagingLine.__table__,
        PackagingOutbound.__table__,
    ])
    db = sessionLocal()
    created = updated = 0
    try:
        for code, name, glass_kg, size, aliases in MATERIALS:
            material = None
            if code:
                material = db.query(PackagingMaterial).filter(
                    PackagingMaterial.article_code == code).first()
            if material is None:
                material = db.query(PackagingMaterial).filter(
                    PackagingMaterial.name == name).first()

            if material is None:
                db.add(PackagingMaterial(
                    article_code=code, name=name, glass_kg=glass_kg,
                    carton_kg=CARTON_KG, bottle_size=size, match_text=aliases,
                    active=True))
                created += 1
            else:
                material.article_code = code or material.article_code
                material.name = name
                material.glass_kg = glass_kg
                material.carton_kg = CARTON_KG
                material.bottle_size = size
                material.match_text = aliases
                material.active = True
                updated += 1
        db.commit()
        print(f"Emballage-stamdata: {created} oprettet, {updated} opdateret "
              f"({len(MATERIALS)} varer i alt).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
