# Python Standard Libraries
import logging

# Installed packages (via pip)
from social_core.exceptions import AuthForbidden

# Internal project dependencies
from .exceptions import ProvisioningError
from .user_creation import (
    fetch_persona,
    provision_user_from_indiv_id,
    link_indiv_id,
)

logger = logging.getLogger(__name__)


def resolve_uid(backend, details, *args, **kwargs):
    """
    Fetch persona data from the external API and override uid with id_persona.

    Has to run before social_user so the UserSocialAuth lookup uses the stable
    immutable identifier id_persona instead of the OAuth provider's sub.
    The fetched persona data is returned in the pipeline dict so provision_user
    can reuse it without a second API call.

    Raises AuthForbidden if identification is missing or the API returns nothing.
    """
    indiv_id = details.get("identification")
    if not indiv_id:
        logger.error("No identification field in details — cannot resolve uid.")
        raise AuthForbidden(backend)

    try:
        persona_data = fetch_persona(indiv_id)
    except ProvisioningError as e:
        logger.error(
            "Failed to resolve uid for indiv_id '%s': %s", indiv_id, e
        )
        raise AuthForbidden(backend) from e

    return {
        "uid": str(persona_data["id_persona"]),
        "persona_data": persona_data,
    }


def provision_user(backend, details, uid, user=None, *args, **kwargs):
    """
    Provision or sync the Django user for this login.

    By the time this runs, resolve_uid has already overridden uid with
    id_persona and stashed persona_data in kwargs, and social_user has
    attempted to find an existing UserSocialAuth link.

    - If user is already populated (returning user): just sync the
      UserIndivId record in case indiv_id changed, and return.
    - Otherwise: delegate to provision_user_from_indiv_id, passing the
      pre-fetched persona data so it doesn't hit the API again.
    """
    indiv_id = details.get("identification")
    persona_data = kwargs.get("persona_data")

    if user is not None:
        link_indiv_id(user, indiv_id)
        return {"user": user}

    try:
        user, enriched_details = provision_user_from_indiv_id(
            indiv_id,
            persona_data=persona_data,
        )
    except ProvisioningError as e:
        logger.error(
            "Provisioning failed for indiv_id '%s': %s", indiv_id, e
        )
        raise AuthForbidden(backend) from e

    return {
        "user": user,
        "details": enriched_details,
    }
