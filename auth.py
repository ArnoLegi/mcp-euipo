"""Gestion de l'authentification OAuth2 auprès de l'EUIPO + helpers HTTP.

Flow OAuth : `client_credentials` (scope `uid`) sur le serveur CAS de l'EUIPO.
Le token (Bearer) est mis en cache avec sa date d'expiration et renouvelé
automatiquement dès qu'il est absent ou expiré.

Deux helpers génériques (`api_get` / `api_post`) ajoutent les en-têtes
d'authentification et exécutent les appels vers les deux API EUIPO utilisées :
  - Trademark Search    : https://api.euipo.europa.eu/trademark-search
  - Goods and Services  : https://api.euipo.europa.eu/goods-and-services
"""
from __future__ import annotations

import asyncio
import logging
import os
import time

import httpx

try:
    from dotenv import load_dotenv

    load_dotenv()  # charge un éventuel .env local (no-op si absent)
except ImportError:  # python-dotenv non installé : on lit l'environnement tel quel
    pass

log = logging.getLogger("mcp_euipo.auth")

# --- Configuration OAuth / API ---------------------------------------------- #
TOKEN_URL = "https://sandbox.euipo.europa.eu/cas-server-webapp/oidc/accessToken"
SCOPE = "uid"

TRADEMARK_BASE = "https://api-sandbox.euipo.europa.eu/trademark-search"
GOODS_SERVICES_BASE = "https://api-sandbox.euipo.europa.eu/goods-and-services"


def _clean(name: str) -> str:
    """Lit une variable d'environnement en retirant espaces et guillemets parasites.

    Erreur fréquente en déploiement : coller la valeur entourée de guillemets
    (EUIPO_CLIENT_ID="xxx"), qui sont alors stockés littéralement.
    """
    value = os.environ.get(name, "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1].strip()
    return value


CLIENT_ID = _clean("EUIPO_CLIENT_ID")
CLIENT_SECRET = _clean("EUIPO_CLIENT_SECRET")


class EUIPOError(RuntimeError):
    """Erreur renvoyée par une API EUIPO (statut HTTP non 2xx)."""


class EUIPOAuthError(EUIPOError):
    """Échec d'authentification OAuth auprès de l'EUIPO."""


# --- Cache du token --------------------------------------------------------- #
_token: str | None = None
_expiry: float = 0.0  # instant (time.monotonic) avant lequel le token reste valide
_lock = asyncio.Lock()

# Marge de sécurité : on renouvelle un peu avant l'expiration réelle.
_EXPIRY_MARGIN = 60.0


async def _fetch_token() -> tuple[str, float]:
    """Demande un nouveau token au serveur CAS (client_credentials)."""
    if not CLIENT_ID or not CLIENT_SECRET:
        raise EUIPOAuthError(
            "Identifiants EUIPO manquants : définissez EUIPO_CLIENT_ID et "
            "EUIPO_CLIENT_SECRET (voir .env.example)."
        )
    data = {
        "grant_type": "client_credentials",
        "scope": SCOPE,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0)) as client:
        resp = await client.post(
            TOKEN_URL,
            data=data,  # form-encoded (application/x-www-form-urlencoded)
            headers={"Accept": "application/json"},
        )
    if resp.status_code in (400, 401, 403):
        raise EUIPOAuthError(
            f"Authentification EUIPO refusée ({resp.status_code}). "
            "Vérifiez EUIPO_CLIENT_ID / EUIPO_CLIENT_SECRET."
        )
    resp.raise_for_status()
    payload = resp.json()
    access_token = payload.get("access_token")
    if not access_token:
        raise EUIPOAuthError("Réponse OAuth EUIPO sans access_token.")
    expires_in = float(payload.get("expires_in", 3600))
    log.info("Nouveau token EUIPO obtenu (expire dans %ss).", int(expires_in))
    return access_token, time.monotonic() + expires_in


async def get_token() -> str:
    """Renvoie un token valide, en le renouvelant si nécessaire (thread/async-safe)."""
    global _token, _expiry
    if _token and time.monotonic() < _expiry - _EXPIRY_MARGIN:
        return _token
    async with _lock:
        # Re-vérification une fois le verrou acquis (un autre appel a pu renouveler).
        if _token and time.monotonic() < _expiry - _EXPIRY_MARGIN:
            return _token
        _token, _expiry = await _fetch_token()
    return _token


async def get_headers() -> dict[str, str]:
    """En-têtes d'authentification pour les appels aux API EUIPO."""
    token = await get_token()
    return {
        "Authorization": f"Bearer {token}",
        "X-IBM-Client-Id": CLIENT_ID,
        "Content-Type": "application/json",
    }


def has_credentials() -> bool:
    return bool(CLIENT_ID and CLIENT_SECRET)


# --- Helpers HTTP génériques ------------------------------------------------ #
_TIMEOUT = httpx.Timeout(60.0, connect=5.0)


def _raise_for_api(resp: httpx.Response) -> None:
    if resp.status_code == 404:
        raise EUIPOError("Ressource introuvable (404).")
    if resp.status_code == 429:
        raise EUIPOError("Quota EUIPO dépassé (429). Réessayez plus tard.")
    if resp.status_code >= 400:
        detail = ""
        try:
            detail = f" — {resp.json()}"
        except Exception:  # noqa: BLE001
            detail = f" — {resp.text[:300]}" if resp.text else ""
        raise EUIPOError(f"Erreur API EUIPO ({resp.status_code}){detail}")


async def api_get(
    base: str, path: str, params: dict | None = None, accept_language: str | None = None
) -> dict:
    """GET authentifié sur une API EUIPO ; renvoie le JSON décodé."""
    headers = await get_headers()
    if accept_language:
        headers["Accept-Language"] = accept_language
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{base}{path}", params=params, headers=headers)
        _raise_for_api(resp)
        return resp.json()


async def api_post(
    base: str, path: str, json: dict | None = None, params: dict | None = None
) -> dict:
    """POST authentifié (corps JSON) sur une API EUIPO ; renvoie le JSON décodé."""
    headers = await get_headers()
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(f"{base}{path}", json=json, params=params, headers=headers)
        _raise_for_api(resp)
        return resp.json()
