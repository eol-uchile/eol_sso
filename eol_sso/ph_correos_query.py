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

class EmailAttribute(BaseModel):
    fecha_registro: str
    nombre: str
    vigencia: str


class NestedEmail(BaseModel):
    email: str
    fecha_registro: str
    vigencia: str
    atributos_email: List[EmailAttribute]


class ExternalPersona(BaseModel):
    id_persona: int
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

        persona_list = api_data.get("getRowsPersona", [])

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


def process_persona_data(persona_list):
    """
    Validate and process the raw persona list returned by fetch_external_persona_data.

    Takes the getRowsPersona list directly, validates the first record against
    ExternalPersona, extracts and splits emails by vigencia, and returns a flat
    clean dictionary ready for consumption by the services layer.

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

    principal_email, other_emails = extract_and_split_emails(persona.email)

    return {
        "id_persona": persona.id_persona,
        "nombres": persona.nombres,
        "paterno": persona.paterno,
        "materno": persona.materno,
        "email_principal": principal_email,
        "emails": other_emails,
    }


def get_persona_by_indiv_id(indiv_id):
    """
    Fetch and process persona data for the given indiv_id.
    Returns a clean dict, or an empty dict if anything failed.
    """
    return process_persona_data(fetch_external_persona_data(indiv_id))
