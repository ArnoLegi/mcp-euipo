"""Outil MCP : validation de termes de produits & services (classification de Nice)."""
from __future__ import annotations

import logging

from auth import GOODS_SERVICES_BASE, EUIPOError, api_post

log = logging.getLogger("mcp_euipo.valider_classe")


async def _suggestions(langue: str, classe: int, texte: str, max_suggestions: int = 20) -> list[dict]:
    """Suggère des termes harmonisés pour un terme non reconnu (POST /terms-suggestion-list)."""
    body = {"language": langue, "classNumber": classe, "texts": [texte]}
    data = await api_post(
        GOODS_SERVICES_BASE,
        "/terms-suggestion-list",
        json=body,
        params={"maxSuggestions": max_suggestions},
    )
    suggestions: list[dict] = []
    for sugg in data.get("suggestions", []):
        for terme in sugg.get("suggestedTerms", []):
            suggestions.append(
                {
                    "text": terme.get("text"),
                    "classNumber": terme.get("classNumber"),
                    "conceptId": terme.get("conceptId"),
                }
            )
    return suggestions


async def valider_classe_nice(
    termes_par_classe: dict[str, list[str]], langue: str = "fr"
) -> dict:
    """Valide des termes de produits & services contre la classification de Nice harmonisée.

    Étape 1 : POST /classification-validation pour savoir si chaque terme est
    harmonisé. Étape 2 : pour chaque terme NON harmonisé, appelle
    POST /terms-suggestion-list afin de proposer des termes acceptés équivalents.

    Args:
        termes_par_classe: Dictionnaire {numéro de classe (str) : [termes]},
            ex. {"33": ["Vins", "Spiritueux"]}.
        langue: Langue source des termes (défaut « fr »).
    """
    if not termes_par_classe:
        return {"erreur": "Aucun terme fourni."}

    # Construction du corps attendu par /classification-validation.
    gs_input = []
    for classe_str, termes in termes_par_classe.items():
        try:
            classe = int(classe_str)
        except (TypeError, ValueError):
            return {"erreur": f"Numéro de classe invalide : {classe_str!r}."}
        gs_input.append({"classNumber": classe, "terms": list(termes)})

    body = {"sourceLanguage": langue, "goodsAndServices": gs_input}
    try:
        data = await api_post(
            GOODS_SERVICES_BASE, "/classification-validation", json=body
        )
    except EUIPOError as e:
        return {"erreur": str(e)}
    except Exception as e:  # noqa: BLE001
        log.exception("valider_classe_nice")
        return {"erreur": f"Erreur inattendue : {e}"}

    resultats: list[dict] = []
    for gs in data.get("goodsAndServices", []):
        classe = gs.get("classNumber")
        for terme in gs.get("terms", []):
            harmonized = bool(terme.get("harmonized"))
            entree = {
                "classe": classe,
                "terme": terme.get("text"),
                "harmonized": harmonized,
                "conceptId": terme.get("conceptId"),
                "suggestions": [],
            }
            if not harmonized:
                entree["errors"] = terme.get("errors", [])
                try:
                    entree["suggestions"] = await _suggestions(
                        langue, classe, terme.get("text", "")
                    )
                except Exception as e:  # noqa: BLE001 — l'échec d'une suggestion ne casse pas tout
                    log.warning("Suggestions indisponibles pour %r : %s", terme.get("text"), e)
            resultats.append(entree)

    return {
        "langue": langue,
        "nombre": len(resultats),
        "termes": resultats,
    }
