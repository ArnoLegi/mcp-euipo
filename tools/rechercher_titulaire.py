"""Outil MCP : recherche de marques de l'UE par nom de titulaire/déposant."""
from __future__ import annotations

import logging

from auth import TRADEMARK_BASE, EUIPOError, api_get
from tools import condenser_marque

log = logging.getLogger("mcp_euipo.rechercher_titulaire")


async def rechercher_par_titulaire_eutm(nom_titulaire: str, page: int = 0) -> dict:
    """Recherche les marques de l'UE déposées par un titulaire (recherche « contient »).

    Construit la requête RSQL `applicants.name==*{nom}*` et interroge l'API
    Trademark Search de l'EUIPO. Renvoie une liste condensée de marques avec la
    pagination (10 résultats par page), au même format que rechercher_marque_eutm.

    Args:
        nom_titulaire: Nom (ou partie du nom) du titulaire/déposant, ex. « LVMH ».
        page: Numéro de page, base 0 (défaut 0).
    """
    nom = (nom_titulaire or "").strip()
    if len(nom) < 2:
        return {"erreur": "Nom de titulaire trop court (au moins 2 caractères)."}

    query = f"applicants.name==*{nom}*"
    params = {"query": query, "page": page, "size": 10}
    try:
        data = await api_get(
            TRADEMARK_BASE, "/trademarks", params=params, accept_language="fr"
        )
    except EUIPOError as e:
        return {"erreur": str(e), "query": query}
    except Exception as e:  # noqa: BLE001
        log.exception("rechercher_par_titulaire_eutm")
        return {"erreur": f"Erreur inattendue : {e}", "query": query}

    marques = [condenser_marque(tm) for tm in data.get("trademarks", [])]
    return {
        "titulaire": nom,
        "query": query,
        "page": data.get("page", page),
        "taille_page": data.get("size", 10),
        "total_resultats": data.get("totalElements", len(marques)),
        "total_pages": data.get("totalPages"),
        "nombre": len(marques),
        "marques": marques,
    }
