"""Outils MCP du serveur EUIPO + helpers de mise en forme partagés."""
from __future__ import annotations


def noms_titulaires(trademark: dict) -> list[str]:
    """Liste des noms de déposants/titulaires d'une marque."""
    return [a.get("name") for a in trademark.get("applicants", []) if a.get("name")]


def condenser_marque(trademark: dict) -> dict:
    """Vue condensée d'une marque issue de GET /trademarks (liste de résultats)."""
    word = (trademark.get("wordMarkSpecification") or {}).get("verbalElement")
    return {
        "numero_demande": trademark.get("applicationNumber"),
        "denomination": word,
        "type_marque": trademark.get("markFeature"),
        "classes_nice": trademark.get("niceClasses", []),
        "titulaires": noms_titulaires(trademark),
        "statut": trademark.get("status"),
        "date_depot": trademark.get("applicationDate"),
        "date_enregistrement": trademark.get("registrationDate"),
        "date_expiration": trademark.get("expiryDate"),
    }
