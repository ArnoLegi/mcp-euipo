"""Outil MCP : fiche détaillée d'une marque de l'UE par son numéro de demande."""
from __future__ import annotations

import logging
import re

from auth import TRADEMARK_BASE, EUIPOError, api_get
from tools import noms_titulaires

log = logging.getLogger("mcp_euipo.detail_marque")

# Numéro de demande : 9 chiffres, ou W + 8 chiffres + lettre optionnelle.
_NUMERO_RE = re.compile(r"^(\d{9}|W\d{8}[A-Za-z]?)$")


def _goods_and_services_fr(detail: dict) -> list[dict]:
    """Extrait les produits & services en français (fallback : toutes langues)."""
    resultat: list[dict] = []
    for gs in detail.get("goodsAndServices", []):
        termes: list[str] = []
        for desc in gs.get("description", []):
            if desc.get("language", "").lower() == "fr":
                termes.extend(desc.get("terms", []))
        if not termes:  # pas de version FR : on prend ce qui est disponible
            for desc in gs.get("description", []):
                termes.extend(desc.get("terms", []))
        resultat.append({"classe": gs.get("classNumber"), "termes": termes})
    return resultat


async def detail_marque_eutm(numero_eutm: str) -> dict:
    """Fiche complète d'une marque de l'UE à partir de son numéro de demande.

    Interroge GET /trademarks/{numero} (en-tête Accept-Language: fr) et renvoie
    la notice détaillée : identité, classes, dates, statut, titulaires, produits
    et services (en français quand disponibles), période d'opposition, oppositions,
    annulations, recours et décisions.

    Args:
        numero_eutm: Numéro de demande EUIPO (9 chiffres, ou « W » + 8 chiffres + lettre).
    """
    numero = (numero_eutm or "").strip().upper().replace(" ", "")
    if not _NUMERO_RE.match(numero):
        return {
            "erreur": "Numéro de marque invalide.",
            "attendu": "9 chiffres, ou « W » suivi de 8 chiffres et d'une lettre optionnelle.",
            "recu": numero_eutm,
        }
    try:
        detail = await api_get(
            TRADEMARK_BASE, f"/trademarks/{numero}", accept_language="fr"
        )
    except EUIPOError as e:
        return {"erreur": str(e), "numero_eutm": numero}
    except Exception as e:  # noqa: BLE001
        log.exception("detail_marque_eutm")
        return {"erreur": f"Erreur inattendue : {e}", "numero_eutm": numero}

    word = (detail.get("wordMarkSpecification") or {}).get("verbalElement")
    return {
        "numero_demande": detail.get("applicationNumber"),
        "denomination": word,
        "type_marque": detail.get("markFeature"),
        "nature_marque": detail.get("markKind"),
        "base_marque": detail.get("markBasis"),
        "classes_nice": detail.get("niceClasses", []),
        "titulaires": noms_titulaires(detail),
        "applicants": detail.get("applicants", []),
        "date_depot": detail.get("applicationDate"),
        "date_enregistrement": detail.get("registrationDate"),
        "date_expiration": detail.get("expiryDate"),
        "statut": detail.get("status"),
        "statut_renouvellement": detail.get("renewalStatus"),
        "produits_et_services": _goods_and_services_fr(detail),
        "opposition_debut": detail.get("oppositionPeriodStartDate"),
        "opposition_fin": detail.get("oppositionPeriodEndDate"),
        "oppositions": detail.get("oppositions", []),
        "annulations": detail.get("cancellations", []),
        "recours": detail.get("appeals", []),
        "decisions": detail.get("decisions", []),
        "publications": detail.get("publications", []),
    }
