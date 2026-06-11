"""Serveur MCP « EUIPO » — point d'entrée.

Expose 5 outils interrogeant les API publiques de l'EUIPO (Office de l'Union
européenne pour la propriété intellectuelle) :
  - rechercher_marque_eutm       : recherche multicritère de marques de l'UE ;
  - detail_marque_eutm           : fiche complète d'une marque par numéro ;
  - rechercher_par_titulaire_eutm: marques d'un titulaire donné ;
  - valider_classe_nice          : validation de termes de produits & services ;
  - recherche_disponibilite      : antériorités bloquantes pour une dénomination.

Transports MCP exposés (même pattern que mcp-inpi) :
  - Streamable HTTP : /mcp   (RECOMMANDÉ pour Claude.ai)
  - SSE (legacy)    : /sse   (+ /messages/)
Santé : GET /health

Lancement local / déploiement (Railway) :  python server.py
Port : variable d'environnement PORT (défaut 8000).
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from auth import has_credentials
from tools.detail_marque import detail_marque_eutm
from tools.disponibilite import recherche_disponibilite
from tools.rechercher_marque import rechercher_marque_eutm
from tools.rechercher_titulaire import rechercher_par_titulaire_eutm
from tools.valider_classe import valider_classe_nice

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
)
log = logging.getLogger("mcp_euipo.server")

HOST = os.environ.get("HOST", "0.0.0.0").strip() or "0.0.0.0"
PORT = int(os.environ.get("PORT", "8000"))

mcp = FastMCP(
    "mcp-euipo",
    host=HOST,
    port=PORT,
    # Mode sans état : chaque requête HTTP est autonome (facilite le scale-out).
    stateless_http=True,
    instructions=(
        "Outils de propriété intellectuelle européenne via les API de l'EUIPO : "
        "recherche et détail des marques de l'Union (EUTM), recherche par titulaire, "
        "validation de termes de produits & services (classification de Nice) et "
        "analyse de disponibilité d'une dénomination."
    ),
)

# Enregistrement des 5 outils (les fonctions conservent leur signature et docstring).
mcp.tool()(rechercher_marque_eutm)
mcp.tool()(detail_marque_eutm)
mcp.tool()(rechercher_par_titulaire_eutm)
mcp.tool()(valider_classe_nice)
mcp.tool()(recherche_disponibilite)


async def health(_request):
    return JSONResponse(
        {
            "status": "ok",
            "service": "mcp-euipo",
            "transports": {"streamable_http": "/mcp", "sse": "/sse"},
            "euipo_credentials_configured": has_credentials(),
        }
    )


def build_app() -> Starlette:
    # On réutilise les routes natives de FastMCP pour chaque transport :
    #   - streamable_app : Route exacte /mcp  (Streamable HTTP)
    #   - sse_app        : Route /sse + Mount /messages/  (SSE legacy)
    streamable_app = mcp.streamable_http_app()  # crée aussi mcp.session_manager
    sse_app = mcp.sse_app()

    @asynccontextmanager
    async def lifespan(_app):
        # Le transport Streamable HTTP exige que le session manager tourne
        # pendant toute la durée de vie de l'application.
        async with mcp.session_manager.run():
            log.info("Session manager Streamable HTTP démarré (/mcp).")
            yield

    routes = [
        Route("/", health, methods=["GET"]),
        Route("/health", health, methods=["GET"]),
        *streamable_app.routes,  # /mcp
        *sse_app.routes,         # /sse + /messages/
    ]
    return Starlette(routes=routes, lifespan=lifespan)


app = build_app()


if __name__ == "__main__":
    if not has_credentials():
        log.warning(
            "EUIPO_CLIENT_ID / EUIPO_CLIENT_SECRET non définis : les outils "
            "échoueront à l'authentification. Renseignez-les dans .env."
        )
    log.info(
        "Démarrage MCP EUIPO sur http://%s:%s (transports : /mcp, /sse)", HOST, PORT
    )
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
