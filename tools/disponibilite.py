"""Outil MCP : recherche de disponibilité d'une dénomination (antériorités EUTM)."""
from __future__ import annotations

import logging

from auth import TRADEMARK_BASE, EUIPOError, api_get
from tools import condenser_marque

log = logging.getLogger("mcp_euipo.disponibilite")

# Statuts considérés « actifs » (susceptibles de bloquer une nouvelle demande).
STATUTS_ACTIFS = [
    "REGISTERED",
    "UNDER_EXAMINATION",
    "APPEALED",
    "RENEWAL_FEE_PAID",
    "EUTM_RENEWED",
]
# Statuts qui rendent une antériorité directement bloquante.
STATUTS_BLOQUANTS = {"REGISTERED", "UNDER_EXAMINATION"}

# Garde-fou : nombre maximal de pages parcourues (size=100 -> 5000 marques max).
_MAX_PAGES = 50
_PAGE_SIZE = 100

_NOTE_PHONETIQUE = (
    "Cette recherche couvre les correspondances verbales (exacte ou « contient ») "
    "sur les marques EUTM actives. L'analyse complète de similarité phonétique et "
    "figurative nécessite une recherche manuelle via eSearch Plus de l'EUIPO."
)


def construire_query(
    denomination: str, classes_nice: list[int] | None, mode: str
) -> str:
    """Construit la requête RSQL de disponibilité (dénomination + statuts actifs + classes)."""
    if mode == "exacte":
        clause_nom = f"wordMarkSpecification.verbalElement=={denomination}"
    else:  # "contient"
        clause_nom = f"wordMarkSpecification.verbalElement==*{denomination}*"

    statuts = ",".join(STATUTS_ACTIFS)
    clauses = [clause_nom, f"status=in=({statuts})"]
    if classes_nice:
        classes = ",".join(str(c) for c in classes_nice)
        clauses.append(f"niceClasses=all=({classes})")
    return ";".join(clauses)


async def recherche_disponibilite(
    denomination: str, classes_nice: list[int], mode: str = "contient"
) -> dict:
    """Évalue la disponibilité d'une dénomination en cherchant les antériorités EUTM actives.

    Interroge l'API Trademark Search (toutes les pages) en filtrant sur les statuts
    actifs, puis classe le résultat :
      - « libre »      : aucune antériorité ;
      - « à vérifier » : uniquement des marques au statut APPEALED ;
      - « bloquée »    : au moins une marque REGISTERED ou UNDER_EXAMINATION.

    Args:
        denomination: Dénomination à tester.
        classes_nice: Classes de Nice à couvrir, ex. [33]. Liste vide = toutes classes.
        mode: « exacte » (égalité stricte) ou « contient » (wildcard). Défaut « contient ».
    """
    denomination = (denomination or "").strip()
    if not denomination:
        return {"erreur": "Dénomination manquante."}
    mode = (mode or "contient").lower()
    if mode not in ("exacte", "contient"):
        return {"erreur": "Mode invalide : utilisez « exacte » ou « contient »."}

    query = construire_query(denomination, classes_nice, mode)

    toutes: list[dict] = []
    page = 0
    try:
        while page < _MAX_PAGES:
            params = {"query": query, "page": page, "size": _PAGE_SIZE}
            data = await api_get(
                TRADEMARK_BASE, "/trademarks", params=params, accept_language="fr"
            )
            toutes.extend(data.get("trademarks", []))
            total_pages = data.get("totalPages", 1) or 1
            page += 1
            if page >= total_pages:
                break
    except EUIPOError as e:
        return {"erreur": str(e), "query": query}
    except Exception as e:  # noqa: BLE001
        log.exception("recherche_disponibilite")
        return {"erreur": f"Erreur inattendue : {e}", "query": query}

    bloquantes = [
        condenser_marque(tm) for tm in toutes if tm.get("status") in STATUTS_BLOQUANTS
    ]
    autres = [
        condenser_marque(tm) for tm in toutes if tm.get("status") not in STATUTS_BLOQUANTS
    ]

    if not toutes:
        disponibilite = "libre"
    elif bloquantes:
        disponibilite = "bloquée"
    else:
        # Aucune bloquante, mais des antériorités existent (typiquement APPEALED).
        disponibilite = "à vérifier"

    return {
        "denomination": denomination,
        "mode": mode,
        "classes_nice": classes_nice or "toutes",
        "query": query,
        "disponibilite": disponibilite,
        "total": len(toutes),
        "anteriorites_bloquantes": bloquantes,
        "autres_anteriorites": autres,
        "note": _NOTE_PHONETIQUE,
    }
