# Python Standard Libraries
import logging
import re
from datetime import datetime, timezone

# Installed packages (via pip)
import unidecode
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)

User = get_user_model()

USERNAME_MAX_LENGTH = 30

def _normalize(text, lowercase=False):
    """
    Remove accents, strip non-alphanumeric characters, and return a list
    of non-empty tokens. Optionally lowercase the result.
 
    _normalize('María José', lowercase=True)  -> ['maria', 'jose']
    _normalize('María José')                  -> ['Maria', 'Jose']
    """
    text = unidecode.unidecode(text)
    if lowercase:
        text = text.lower()
    text = re.sub(r"[^a-zA-Z0-9]", " ", text)
    return [token for token in text.split() if token]
 
 
def _available(username):
    """Return True if the username is within length limits and not already taken."""
    return (
        len(username) <= USERNAME_MAX_LENGTH
        and not User.objects.filter(username=username).exists()
    )
 
 
def _join(*parts):
    """Join non-empty parts with underscores."""
    return "_".join(p for p in parts if p)
 
 
def _first_available_numbered(base, limit=10000):
    """
    Append 1, 2, 3, … to base until an available username is found.
    base is truncated so there's always room for the numeric suffix.
    Returns the username, or None if every number up to limit is taken.
    """
    base = base[: USERNAME_MAX_LENGTH - 5].rstrip("_")
    for i in range(1, limit):
        candidate = f"{base}{i}"
        if _available(candidate):
            return candidate
    return None
 
 
def _progressive_prefix(tokens, base, suffix_tokens):
    """
    Try progressively longer prefixes of each extra token appended to base,
    combined with suffix_tokens joined after.
 
    Used for strategies 2, 3, and 4 where we incrementally consume characters
    from additional name parts until we find an available username or hit the length cap.
 
    Example with base='juan', tokens=['carlos'], suffix_tokens=['perez']:
        tries: juan_c_perez, juan_ca_perez, juan_car_perez ... juan_carlos_perez
    """
    current = base
    for token in tokens:
        current += "_"
        for i in range(1, len(token) + 1):
            candidate = _join(current + token[:i], *suffix_tokens)
            if len(candidate) > USERNAME_MAX_LENGTH:
                break
            if _available(candidate):
                return candidate
    return None
 
 
def generate_username(user_data):
    """
    Generate a unique username from persona data using a tiered fallback strategy.
 
    Strategies attempted in order:
      0. Single name only (+ numeric suffix if needed)
      1. first_name_last_name
      2. first_name_last_name + progressive chars from extra last names
      3. first_name + progressive chars from extra first names + last_name
      4. first_name + progressive extra first names + last_name + progressive extra last names
      5. first_name_last_name + numeric suffix (1-9999)
 
    Accepts either:
      - {'nombreCompleto': 'Juan Carlos Perez Soto'}
      - {'nombres': 'Juan Carlos', 'apellidoPaterno': 'Perez', 'apellidoMaterno': 'Soto'}
    """
    if "nombreCompleto" in user_data:
        tokens = _normalize(user_data["nombreCompleto"], lowercase=True)
        if len(tokens) == 1:
            # Strategy 0: only one token available
            name = tokens[0]
            if _available(name):
                return name
            result = _first_available_numbered(name)
            if result:
                return result
            raise Exception(f"Could not generate username for: {user_data}")
 
        mid = len(tokens) // 2
        first_names = tokens[:mid]
        last_names = tokens[mid:]
    else:
        first_names = _normalize(user_data.get("nombres", ""))
        last_names = _normalize(
            (user_data.get("apellidoPaterno") or "")
            + " "
            + (user_data.get("apellidoMaterno") or "")
        )
 
    if not first_names:
        first_names = ["user"]
    if not last_names:
        last_names = ["unknown"]
 
    f0 = first_names[0]
    l0 = last_names[0]
    extra_first = first_names[1:]
    extra_last = last_names[1:]
 
    # Strategy 1: first_last
    candidate = _join(f0, l0)
    if _available(candidate):
        return candidate
 
    # Strategy 2: first_last + progressive chars from extra last names
    result = _progressive_prefix(extra_last, _join(f0, l0), [])
    if result:
        return result
 
    # Strategy 3: first + progressive extra first names + last
    result = _progressive_prefix(extra_first, f0, [l0])
    if result:
        return result
 
    # Strategy 4: first + progressive extra firsts + last + progressive extra lasts
    current_first = f0
    for extra_f in extra_first:
        current_first += "_"
        for i in range(1, len(extra_f) + 1):
            partial_first = current_first + extra_f[:i]
            result = _progressive_prefix(extra_last, _join(partial_first, l0), [])
            if result:
                return result
            if len(_join(partial_first, l0)) > USERNAME_MAX_LENGTH:
                break
 
    # Strategy 5: first_last + numeric suffix
    result = _first_available_numbered(_join(f0, l0))
    if result:
        return result
 
    raise Exception(f"Could not generate username for: {user_data}")


# Emails

def _parse_fecha(fecha_str):
    """
    Parse an ISO 8601 datetime string (e.g. "2020-01-03T12:33:44-03:00")
    into a timezone-aware datetime for sorting. Returns datetime.min on failure.
    """
    try:
        return datetime.fromisoformat(fecha_str)
    except (ValueError, TypeError):
        return datetime.min.replace(tzinfo=timezone.utc)


def extract_and_split_emails(validated_email_list):
    """
    Split a validated list of NestedEmail objects into a principal email
    and a list of remaining emails, filtering only on structural validity
    (vigencia == "1").

    Returns:
        (email_principal, list_of_other_emails)
        email_principal may be "" if no active PRINCIPAL email exists.
    """
    email_principal = ""
    others = []

    for node in validated_email_list:
        if node.vigencia != "1":
            continue

        is_principal = any(
            attr.vigencia == "1" and attr.nombre == "PRINCIPAL"
            for attr in node.atributos_email
        )

        if is_principal and not email_principal:
            email_principal = node.email
        else:
            others.append((node.email, node.fecha_registro))

    # Most recent first
    others.sort(key=lambda pair: _parse_fecha(pair[1]), reverse=True)
    other_emails = [email for email, _ in others]

    return email_principal, other_emails
