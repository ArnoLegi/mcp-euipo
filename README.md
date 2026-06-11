# mcp-euipo

Serveur **MCP (Model Context Protocol)** en Python exposant les API publiques de
l'**EUIPO** (Office de l'Union européenne pour la propriété intellectuelle) :
recherche et détail de marques de l'Union (EUTM), recherche par titulaire,
validation de termes de produits & services (classification de Nice) et analyse
de disponibilité d'une dénomination.

Conçu pour être branché sur Claude.ai (transports Streamable HTTP `/mcp` et SSE
`/sse`) et déployable sur Railway.

## Outils exposés

| Outil | Description |
|-------|-------------|
| `rechercher_marque_eutm` | Recherche multicritère (dénomination, classes de Nice, statut, titulaire) construisant une requête RSQL. |
| `detail_marque_eutm` | Fiche complète d'une marque par numéro de demande (produits & services en français). |
| `rechercher_par_titulaire_eutm` | Marques déposées par un titulaire (`applicants.name`). |
| `valider_classe_nice` | Valide des termes contre la classification de Nice harmonisée et propose des termes acceptés. |
| `recherche_disponibilite` | Antériorités actives bloquantes pour une dénomination (statut : libre / à vérifier / bloquée). |

## Architecture

```
mcp-euipo/
├── server.py                  ← point d'entrée MCP (FastMCP + Starlette + uvicorn)
├── auth.py                    ← OAuth2 client_credentials + helpers HTTP EUIPO
├── tools/
│   ├── __init__.py            ← helpers de mise en forme partagés
│   ├── rechercher_marque.py
│   ├── detail_marque.py
│   ├── rechercher_titulaire.py
│   ├── valider_classe.py
│   └── disponibilite.py
├── requirements.txt
├── .env.example
├── Procfile                   ← web: python server.py
└── README.md
```

## Authentification

Flow OAuth2 `client_credentials` (scope `uid`) sur le serveur CAS de l'EUIPO :

```
POST https://euipo.europa.eu/cas-server-webapp/oidc/accessToken
grant_type=client_credentials&scope=uid&client_id=...&client_secret=...
```

Le token (Bearer) est mis en cache avec son expiration et renouvelé
automatiquement. Chaque appel aux API EUIPO utilise les en-têtes :

```
Authorization: Bearer <token>
X-IBM-Client-Id: <EUIPO_CLIENT_ID>
Content-Type: application/json
```

## API EUIPO utilisées

- **Trademark Search** — `https://api.euipo.europa.eu/trademark-search`
  (`GET /trademarks`, `GET /trademarks/{applicationNumber}`), requêtes en
  syntaxe **RSQL** (`;` = AND, `,` = OR, `*` = wildcard).
- **Goods and Services** — `https://api.euipo.europa.eu/goods-and-services`
  (`POST /classification-validation`, `POST /terms-suggestion-list`).

## Installation & lancement local

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows (PowerShell : .venv\Scripts\Activate.ps1)
pip install -r requirements.txt

copy .env.example .env         # puis renseigner EUIPO_CLIENT_ID / EUIPO_CLIENT_SECRET
python server.py
```

Le serveur écoute sur `http://0.0.0.0:8000` par défaut (variable `PORT`).
Vérification : `GET http://localhost:8000/health`.

## Déploiement Railway

Le `Procfile` (`web: python server.py`) et la lecture de la variable `PORT`
rendent le service directement déployable sur Railway. Définir
`EUIPO_CLIENT_ID` et `EUIPO_CLIENT_SECRET` dans les variables d'environnement
du service.

## Note sur la disponibilité

`recherche_disponibilite` couvre les correspondances **verbales** (exacte ou
« contient ») sur les marques EUTM actives. L'analyse complète de similarité
**phonétique** et **figurative** nécessite une recherche manuelle via
[eSearch Plus](https://euipo.europa.eu/eSearch/) de l'EUIPO.
