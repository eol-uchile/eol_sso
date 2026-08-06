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

    Args:
        backend: the PSA backend instance running this auth flow (e.g.
            UchileOAuth2Backend). Only used here to construct AuthForbidden,
            which requires the backend that raised it.
        details: dict built earlier in the pipeline by PSA's social_details step,
            using the backend get_user_details function.
            Expected to contain "identification", the raw ID the external
            API is keyed on.
        *args, **kwargs: the rest of the pipeline's accumulated running state
            (e.g. strategy, request, response, is_new, social, ...). Unused
            here, but required since PSA calls every step with the full
            current kwargs.
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


def provision_user(backend, details, user=None, *args, **kwargs):
    """
    Provision or sync the Django user for this login.

    By the time this runs, resolve_uid has already overridden uid with
    id_persona and stashed persona_data in kwargs, and social_user has
    attempted to find an existing UserSocialAuth link.

    - If user is already populated (returning user): just sync the
      UserIndivId record in case indiv_id changed, and return.
    - Otherwise: delegate to provision_user_from_indiv_id, passing the
      pre-fetched persona data so it doesn't hit the API again.

    Args:
        backend: the PSA backend instance running this auth flow. Used to
            construct AuthForbidden on provisioning failure.
        details: dict built earlier in the pipeline by PSA's social_details
            step using the  backend's get_user_details function.
            Only "identification" is expected here, the persona API is used
            as the source for the personal info, so this step replaces 
            "details" for any pipeline steps still to come.
        user: the Django User already associated with this auth attempt, if
            any. Populated by social_user when an existing UserSocialAuth
            link was found, OR when the request came from an already
            logged-in session (the "connect account" flow from account
            settings). None on a brand-new login with no existing link.
        *args, **kwargs: the rest of the pipeline's running state. In
            particular, kwargs["persona_data"] holds the dict resolve_uid
            fetched earlier, reused here to avoid a second API call.
    """
    indiv_id = details.get("identification")
    persona_data = kwargs.get("persona_data")

    if user is not None:
        link_indiv_id(user, indiv_id)
        return {"user": user}

    try:
        user, user_data = provision_user_from_indiv_id(
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
        "details": user_data,
    }
