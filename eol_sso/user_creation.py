# Python Standard Libraries
import logging
from datetime import datetime, timezone

# Installed packages (via pip)
from django.contrib.auth import get_user_model
from django.contrib.auth.models import BaseUserManager
from django.core.validators import validate_email
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction

# Edx dependencies
from openedx.core.djangoapps.user_authn.views.registration_form import AccountCreationForm
from common.djangoapps.student.helpers import do_create_account

# Internal project dependencies
from .backends import UchileOAuth2Backend
from .ph_correos_query import get_persona_by_indiv_id
from .models import UserIndivId
from .utils import generate_username
from .exceptions import (
    AccountCreationError,
    NoValidEmailError,
    PersonaNotFoundError,
)

logger = logging.getLogger(__name__)

User = get_user_model()


def _is_valid_email(address):
    """Return True if the address passes Django's email validation."""
    try:
        validate_email(address)
        return True
    except DjangoValidationError:
        return False


def fetch_persona(indiv_id):
    """
    Query the external API for persona data by indiv_id.

    Returns the persona dict on success.
    Raises PersonaNotFoundError if the API returns nothing.
    """
    persona_data = get_persona_by_indiv_id(indiv_id)

    if not persona_data:
        raise PersonaNotFoundError(
            f"External API returned no data for identification '{indiv_id}'."
        )

    return persona_data


def select_email_for_account(email_principal, emails):
    """
    Select the best usable email for account creation.

      1. If email_principal exists and passes Django validation, use it
      2. Otherwise take the first email that passes Django validation
         (emails are already recency-ordered, so this is the most recent valid one)
      3. If nothing passes validation, raise NoValidEmailError.
    """
    if email_principal and _is_valid_email(email_principal):
        return email_principal

    if email_principal:
        logger.warning(
            "PRINCIPAL email '%s' failed validation — falling back to other emails.",
            email_principal,
        )

    for candidate in emails or []:
        if _is_valid_email(candidate):
            return candidate

    raise NoValidEmailError(
        "No valid email found after validation of all candidates."
    )


def build_user_data(persona_data, resolved_email, user=None):
    """
    Construct the enriched dict from persona data and resolved email.
    A username is generated only for new accounts.

    Returns the enriched dict.
    """
    first_name = persona_data["nombres"]
    last_name = f"{persona_data['paterno']} {persona_data['materno']}".strip()
    fullname = f"{first_name} {last_name}".strip()

    user_data = {
        "email": user.email if user else resolved_email,
        "first_name": first_name,
        "last_name": last_name,
        "fullname": fullname,
        "id_persona": persona_data["id_persona"],
        "indiv_id": persona_data["indiv_id"],
    }

    if user is None:
        # Pass structured name parts so generate_username knows the exact
        # first-name / surname boundary instead of guessing from a full string.
        user_data["username"] = generate_username(
            {
                "nombres": persona_data["nombres"],
                "apellidoPaterno": persona_data["paterno"],
                "apellidoMaterno": persona_data["materno"],
            }
        )
        logger.info("Generated username '%s' for new user.", user_data["username"])
    else:
        user_data["username"] = user.username

    return user_data


def find_existing_user(candidate_emails):
    """
    Look up a Django user matching any of the candidate emails.

    Emails already linked to an existing UchileOAuth2Backend social-auth
    identity are excluded from matching before lookup — prevents linking
    a new SSO identity to an account already claimed by someone else
    (e.g. if an email is later reassigned to a different person on the
    provider side).

    - No match: return None.
    - Exactly one match: return it.
    - Multiple matches: resolve by most recent last_login. Accounts that
      never logged in (last_login is None) are treated as oldest and
      only chosen as a last resort.

    Args:
        candidate_emails: emails to match against the resolved account
            email plus any other emails on file for the persona.

    Returns:
        A User instance, or None if no candidate email matched anyone.
    """
    linked_emails = set(
        User.objects.filter(
            email__in=candidate_emails,
            social_auth__provider=UchileOAuth2Backend.name,
        ).values_list('email', flat=True)
    )
    if linked_emails:
        logger.warning(
            "Excluding already-linked email(s) %s from candidates.", linked_emails,
        )
        candidate_emails = [e for e in candidate_emails if e not in linked_emails]

    matched_users = list(User.objects.filter(email__in=candidate_emails))

    if not matched_users:
        return None

    if len(matched_users) == 1:
        return matched_users[0]

    chosen = max(
        matched_users,
        key=lambda u: u.last_login or datetime.min.replace(tzinfo=timezone.utc),
    )
    logger.info(
        "Multiple Django users matched candidate emails %s, "
        "chose '%s' by most recent last_login.",
        candidate_emails, chosen.username,
    )
    return chosen


def create_and_activate_user(username, email, fullname):
    """
    Create a new Open edX user via AccountCreationForm + do_create_account,
    then immediately activate the account.

    A random password is set on the account — users authenticate exclusively
    via SSO and never use it directly.

    Returns the created User instance.
    Raises AccountCreationError if form validation fails.
    """
    form = AccountCreationForm(
        data={
            "username": username,
            "email": email,
            "password": BaseUserManager().make_random_password(12),
            "name": fullname,
        },
        tos_required=False,
    )

    if not form.is_valid():
        raise AccountCreationError(
            f"AccountCreationForm validation failed for username '{username}'.",
            form_errors=form.errors,
        )

    new_user, _, reg = do_create_account(form)
    reg.activate()
    reg.save()

    logger.info("Created and activated new user '%s'.", username)

    return new_user

def link_indiv_id(user, indiv_id):
    """
    Associate indiv_id with user. If indiv_id is currently associated with a different
    user (e.g. a stale record), that association is moved to the current user.
    """
    with transaction.atomic():
        previous_owner = (
            UserIndivId.objects.filter(indiv_id=indiv_id)
            .exclude(user=user)
            .first()
        )
        if previous_owner:
            logger.info(
                "Removing stale UserIndivId link: indiv_id '%s' was linked to user '%s'.",
                indiv_id, previous_owner.user_id,
            )
            previous_owner.delete()

        UserIndivId.objects.update_or_create(
            user=user,
            defaults={"indiv_id": indiv_id},
        )
        logger.info("Synced UserIndivId for user '%s' → '%s'.", user.username, indiv_id)

def provision_user_from_indiv_id(indiv_id, existing_user=None, persona_data=None):
    """
    Full user provisioning flow starting from an indiv_id.

    1. Fetch persona data from the external API (skipped if persona_data
       is already provided, useful when the pipeline has pre-fetched it)
    2. Select the best usable email
    3. Resolve the user, already linked (existing_user), matched by email, or to be created
    4. Build enriched user_data (generating a username only for new accounts)
    5. Create the account if needed, then sync the UserIndivId record

    The account creation and profile sync run inside a single transaction so a failure
    can't leave a user without their indiv_id link. The external API call is deliberately
    kept outside the transaction.

    Returns:
        (user, user_data), the Django user and the enriched user_data dict.
    """
    if persona_data is None:
        persona_data = fetch_persona(indiv_id)

    resolved_email = select_email_for_account(
        email_principal=persona_data.get("email_principal"),
        emails=persona_data.get("emails", []),
    )

    user = existing_user
    if user is None:
        # Cleans up email_principal in case there isn't one.
        principal = persona_data.get("email_principal")
        candidate_emails = ([principal] if principal else []) + persona_data.get("emails", [])
        user = find_existing_user(candidate_emails)
        if user is not None:
            logger.info(
                "Found existing user '%s' via email match — skipping creation.",
                user.username,
            )

    user_data = build_user_data(persona_data, resolved_email, user=user)

    if user is None:
        with transaction.atomic():
            user = create_and_activate_user(
                username=user_data["username"],
                email=resolved_email,
                fullname=user_data["fullname"],
            )
            link_indiv_id(user, indiv_id)
    else:
        link_indiv_id(user, indiv_id)

    return user, user_data
