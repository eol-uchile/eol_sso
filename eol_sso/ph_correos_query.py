# Python Standard Libraries
import logging
import requests
from typing import List

# Installed packages (via pip)
from django.conf import settings
from pydantic import BaseModel, ValidationError

# Internal project dependencies
from .utils import extract_and_split_emails

logger = logging.getLogger(__name__)

class EmailType(BaseModel):
    id_tipo_email: int
    nombre: str


class EmailAttribute(BaseModel):
    fecha_registro: str
    vigencia: str
    tipo_email: List[EmailType]


class NestedEmail(BaseModel):
    email: str
    fecha_registro: str
    vigencia: str
    atributos_email: List[EmailAttribute]


class ExternalPersona(BaseModel):
    id_persona: int
    indiv_id: str
    nombres: str
    paterno: str
    materno: str
    nombre_social: str = ""
    email: List[NestedEmail]


def fetch_external_persona_data(indiv_id):
    """
    Query the external API using indiv_id to retrieve persona information.

    Returns the raw list of persona records getRowsPersona, or an empty list if
    anything goes wrong.
    """
    headers = {
        'AppKey': settings.SSOLOGIN_UCHILE_KEY,
        'Origin': settings.LMS_ROOT_URL
    }
    params = {"indiv_id": f'"{indiv_id}"'}

    try:
        response = requests.get(settings.BASE_EOL_SSO_API_URL, headers=headers, params=params, timeout=10)
        response.raise_for_status()

        payload = response.json()
        api_data = payload.get("data")

        if api_data is None:
            logger.error(
                "External API returned no data. Errors: %s", payload.get("errors")
            )
            return []

        rows_persona = api_data.get("getRowsPersona", {})
        persona_list = rows_persona.get("persona", [])

        if not persona_list:
            logger.warning(
                "External API returned an empty persona list for indiv_id: %s", indiv_id
            )
        return persona_list

    except requests.exceptions.RequestException as e:
        logger.error(
            "Failed to connect to external API for indiv_id %s: %s", indiv_id, e
        )
        return []


def fetch_external_persona_data_bulk(indiv_ids):
    """
    Query the external API for multiple indiv_ids in a single request.

    Same endpoint as fetch_external_persona_data, but indiv_id is passed as a
    comma-joined, quoted list instead of a single value. indiv_ids the API
    doesn't recognize are simply absent from the response — not an error.

    Returns the raw list of persona records (getRowsPersona.persona), or an
    empty list if anything goes wrong.
    """
    headers = {
        'AppKey': settings.SSOLOGIN_UCHILE_KEY,
        'Origin': settings.LMS_ROOT_URL
    }
    quoted_values = [f'"{v}"' for v in indiv_ids]
    params = {"indiv_id": ",".join(quoted_values)}

    try:
        response = requests.get(settings.BASE_EOL_SSO_API_URL, headers=headers, params=params, timeout=10)
        response.raise_for_status()

        payload = response.json()
        api_data = payload.get("data")

        if api_data is None:
            logger.error(
                "External API returned no data for bulk query. Errors: %s", payload.get("errors")
            )
            return []

        rows_persona = api_data.get("getRowsPersona", {})
        persona_list = rows_persona.get("persona", [])

        if not persona_list:
            logger.warning(
                "External API returned an empty persona list for bulk query of %d indiv_ids.",
                len(indiv_ids),
            )
        return persona_list

    except requests.exceptions.RequestException as e:
        logger.error("Failed to connect to external API for bulk query: %s", e)
        return []


def _persona_to_dict(persona):
    """Shape a validated ExternalPersona into the clean dict shape used everywhere else."""
    principal_email, other_emails = extract_and_split_emails(persona.email)
    return {
        "id_persona": persona.id_persona,
        "indiv_id": persona.indiv_id,
        "nombres": persona.nombres,
        "paterno": persona.paterno,
        "materno": persona.materno,
        "email_principal": principal_email,
        "emails": other_emails,
    }


def process_persona_data(persona_list):
    """
    Validate and process the raw persona list returned by fetch_external_persona_data.
    Takes the getRowsPersona list directly, validates the first record against
    ExternalPersona, and returns a flat clean dictionary ready for consumption
    by the services layer.

    Returns an empty dict if validation fails or the list is empty.
    """
    if not persona_list:
        return {}

    raw_persona = persona_list[0]

    try:
        persona = ExternalPersona.model_validate(raw_persona)
    except ValidationError as e:
        logger.error("Persona validation failed: %s", e)
        return {}

    return _persona_to_dict(persona)


def process_persona_data_bulk(persona_list):
    """
    Validate and process a list of persona records from a bulk API call.

    Unlike process_persona_data, every record here is validated independently, one
    invalid record is logged and skipped without discarding the rest of the batch.

    Returns a dict keyed by indiv_id.
    """
    results = {}
    for raw_persona in persona_list:
        try:
            persona = ExternalPersona.model_validate(raw_persona)
        except ValidationError as e:
            logger.error("Persona validation failed in bulk fetch: %s", e)
            continue
        results[persona.indiv_id] = _persona_to_dict(persona)
    return results


def get_persona_by_indiv_id(indiv_id):
    """
    Fetch and process persona data for the given indiv_id.
    Returns a clean dict, or an empty dict if anything failed.
    """
    return process_persona_data(fetch_external_persona_data(indiv_id))


def get_persona_by_indiv_id_bulk(indiv_ids):
    """
    Fetch and process persona data for multiple indiv_ids in one API call.

    Returns a dict keyed by indiv_id -> clean persona dict. indiv_ids not
    found in the API response are simply absent from the result, callers
    should treat a missing key as "not found", the same as a single lookup
    returning an empty dict.
    """
    return process_persona_data_bulk(fetch_external_persona_data_bulk(indiv_ids))
