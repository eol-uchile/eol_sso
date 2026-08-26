# Python Standard Libraries
import logging
import requests
from typing import List

# Installed packages (via pip)
from django.conf import settings
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

class NestedPasaporte(BaseModel):
    usuario: str


class ExternalPersonaByUsername(BaseModel):
    id_persona: int
    indiv_id: str
    pasaporte: List[NestedPasaporte] = Field(min_length=1)


def get_persona_by_username_bulk(usernames):
    """
    Fetch and process persona data for multiple username in one API call.

    Query the external API for multiple usuarios in a single request and validates their
    format. Every record here is validated independently, one invalid record is logged and
    skipped without discarding the rest of the batch.

    Returns a dict keyed by username -> clean persona dict. username not
    found in the API response are simply absent from the result, callers
    should treat a missing key as "not found", the same as a single lookup
    returning an empty dict.
    """
    headers = {
        'AppKey': settings.SSOLOGIN_UCHILE_KEY,
        'Origin': settings.LMS_ROOT_URL
    }
    quoted_values = [f'"{v}"' for v in usernames]
    params = {"usuario": ",".join(quoted_values)}

    try:
        response = requests.get(settings.BASE_EOL_SSO_API_URL_PROFILE, headers=headers, params=params, timeout=10)
        response.raise_for_status()

    except requests.exceptions.RequestException as e:
        logger.error("Failed to connect to external API for bulk query: %s", e)
        return {}

    payload = response.json()
    api_data = payload.get("data")

    if api_data is None:
        logger.error(
            "External API returned no data for bulk query. Errors: %s", payload.get("errors")
        )
        return {}

    rows_persona = api_data.get("getRowsPersona", {})
    persona_list = rows_persona.get("persona", [])

    if not persona_list:
        logger.warning(
            "External API returned an empty persona list for bulk query of %d usernames.",
            len(usernames),
        )
        return {}

    # Validate persona format
    results = {}
    for raw_persona in persona_list:
        try:
            persona = ExternalPersonaByUsername.model_validate(raw_persona)
        except ValidationError as e:
            logger.error("Persona validation failed in bulk fetch: %s", e)
            continue
        entry = {
            "id_persona": persona.id_persona,
            "indiv_id": persona.indiv_id,
            "usuario": persona.pasaporte[0].usuario
        }
        results[entry["usuario"]] = entry

    return results
