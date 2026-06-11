"""Outil MCP : recherche de marques de l'UE (EUTM) par critères combinés."""
from __future__ import annotations

import logging

from auth import TRADEMARK_BASE, EUIPOError, api_get
from tools import condenser_marque

log = logging.getLogger("mcp_euipo.rechercher_marque")

# Statuts acceptés par l'API Trademark Search (pour validation/erreur explicite).
STATUTS_VALIDES = {
    "UNDER_EXAMINATION",
    "REFUSED",
    "APPEALED",
    "REGISTERED",
    "NOTIFICATION_OF_EXPIRY_OF_EUTM",
    "RENEWAL_FEE_PAID",
    "EUTM_RENEWED",
    "EUTM_EXPIRED",
}


def construire_query(
    denomination: str | None = None,
    classes_nice: list[int] | None = None,
    statut: str | None = None,
    titulaire: str | None = None,
) -> str:
    """Construit une requête RSQL en combinant les filtres non vides avec « ; » (AND)."""
    clauses: list[str] = []
    if denomination:
        clauses.append(f"wordMarkSpecification.verbalElement==*{denomination}*")
    if classes_nice:
        classes = ",".join(str(c) for c in classes_nice)
        clauses.append(f"niceClasses=all=({classes})")
    if statut:
        clauses.append(f"status=={statut.upper()}")
    if titulaire:
        clauses.append(f"applicants.name==*{titulaire}*")
    return ";".join(clauses)


async def rechercher_marque_eutm(
    denomination: str,
    classes_nice: list[int] | None = None,
    statut: str | None = None,
    titulaire: str | None = None,
    page: int = 0,
) -> dict:
    """Recherche des marques de l'Union européenne (EUTM) par critères combinés.

    Construit une requête RSQL à partir des filtres fournis (dénomination en
    « contient », classes de Nice, statut, titulaire) et interroge l'API
    Trademark Search de l'EUIPO. Renvoie une liste condensée de marques avec la
    pagination (10 résultats par page).

    Args:
        denomination: Élément verbal recherché (recherche « contient », ex. « BORDEAUX »).
        classes_nice: Classes de Nice à filtrer, ex. [33] ou [33, 35] (optionnel).
        statut: Statut EUIPO, ex. « REGISTERED », « UNDER_EXAMINATION » (optionnel).
        titulaire: Nom (ou partie) du titulaire/déposant, ex. « LVMH » (optionnel).
        page: Numéro de page, base 0 (défaut 0).
    """
    denomination = (denomination or "").strip()
    if not denomination and not titulaire:
        return {"erreur": "Fournissez au moins une dénomination ou un titulaire."}
    if statut and statut.upper() not in STATUTS_VALIDES:
        return {
            "erreur": f"Statut invalide : {statut}.",
            "statuts_valides": sorted(STATUTS_VALIDES),
        }

    query = construire_query(denomination or None, classes_nice, statut, titulaire)
    params = {"query": query, "page": page, "size": 10}
    try:
        data = await api_get(
            TRADEMARK_BASE, "/trademarks", params=params, accept_language="fr"
        )
    except EUIPOError as e:
        return {"erreur": str(e), "query": query}
    except Exception as e:  # noqa: BLE001
        log.exception("rechercher_marque_eutm")
        return {"erreur": f"Erreur inattendue : {e}", "query": query}

    marques = [condenser_marque(tm) for tm in data.get("trademarks", [])]
    return {
        "query": query,
        "page": data.get("page", page),
        "taille_page": data.get("size", 10),
        "total_resultats": data.get("totalElements", len(marques)),
        "total_pages": data.get("totalPages"),
        "nombre": len(marques),
        "marques": marques,
    }
