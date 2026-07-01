# Python Standard Libraries
from datetime import timedelta
from unittest import mock
from unittest.mock import patch

# Installed packages (via pip)
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from social_core.exceptions import AuthForbidden
from social_django.utils import load_strategy

# Internal project dependencies
from eol_sso.backends import UchileOAuth2Backend
from eol_sso.exceptions import (
    NoValidEmailError,
    PersonaNotFoundError,
)
from eol_sso.models import UserIndivId
from eol_sso.pipeline import provision_user, resolve_uid
from eol_sso.ph_correos_query import (
    EmailAttribute,
    NestedEmail,
    extract_and_split_emails,
    process_persona_data,
)
from eol_sso.user_creation import (
    _is_valid_email,
    find_existing_user,
    provision_user_from_indiv_id,
    select_email_for_account,
    link_indiv_id,
)
from eol_sso.utils import generate_username


User = get_user_model()

# A persona dict shaped as get_persona_by_indiv_id would return it
FAKE_PERSONA = {
    "id_persona": 999,
    "nombres": "Juan Carlos",
    "paterno": "Pérez",
    "materno": "Soto",
    "email_principal": "juan.perez@test.cl",
    "emails": ["jperez@gmail.com"],
    "indiv_id": "12345678-9"
}

INDIV_ID = "12345678-9"

def make_email_node(address, fecha, vigencia="1", principal=False):
    """Build a NestedEmail pydantic object for the email-split tests."""
    attrs = []
    if principal:
        attrs.append(
            EmailAttribute(fecha_registro=fecha, nombre="PRINCIPAL", vigencia="1")
        )
    return NestedEmail(
        email=address,
        fecha_registro=fecha,
        vigencia=vigencia,
        atributos_email=attrs,
    )

def make_raw_email(address, fecha, vigencia="1", principal=False):
    """Build a raw email dict as the API would send it for process_persona_data."""
    attrs = []
    if principal:
        attrs.append(
            {"fecha_registro": fecha, "nombre": "PRINCIPAL", "vigencia": "1"}
        )
    return {
        "email": address,
        "fecha_registro": fecha,
        "vigencia": vigencia,
        "atributos_email": attrs,
    }


class EmailValidationTests(SimpleTestCase):
    """_is_valid_email wraps Django's validator."""

    def test_valid_addresses(self):
        self.assertTrue(_is_valid_email("a@b.cl"))
        self.assertTrue(_is_valid_email("first.last+tag@uchile.com"))

    def test_invalid_addresses(self):
        self.assertFalse(_is_valid_email("invalid-email"))
        self.assertFalse(_is_valid_email("missing@example"))
        self.assertFalse(_is_valid_email("@uchile.cl"))
        self.assertFalse(_is_valid_email("a.@uchile.cl"))
        self.assertFalse(_is_valid_email(""))


class ExtractAndSplitEmailsTests(SimpleTestCase):
    """Test extract_and_split_emails, vigencia filter, principal, recency order."""

    def test_principal_extracted_others_recency_ordered(self):
        nodes = [
            make_email_node("old@uchile.cl", "2018-01-01T00:00:00-03:00"),
            make_email_node("principal@uchile.cl", "2020-01-01T00:00:00-03:00", principal=True),
            make_email_node("recent@uchile.cl", "2023-06-01T00:00:00-03:00"),
            make_email_node("mid@uchile.cl", "2021-03-01T00:00:00-03:00"),
        ]
        principal, others = extract_and_split_emails(nodes)

        self.assertEqual(principal, "principal@uchile.cl")
        self.assertEqual(others, ["recent@uchile.cl", "mid@uchile.cl", "old@uchile.cl"])

    def test_inactive_records_dropped(self):
        nodes = [
            make_email_node("live@uchile.cl", "2022-01-01T00:00:00-03:00"),
            make_email_node("inactive@uchile.cl", "2024-01-01T00:00:00-03:00", vigencia="0"),
        ]
        principal, others = extract_and_split_emails(nodes)

        self.assertEqual(principal, "")
        self.assertEqual(others, ["live@uchile.cl"])
        self.assertNotIn("inactive@uchile.cl", others)

    def test_no_principal_all_in_others(self):
        nodes = [
            make_email_node("a@uchile.cl", "2019-01-01T00:00:00-03:00"),
            make_email_node("b@uchile.cl", "2022-01-01T00:00:00-03:00"),
        ]
        principal, others = extract_and_split_emails(nodes)

        self.assertEqual(principal, "")
        self.assertEqual(others, ["b@uchile.cl", "a@uchile.cl"])

    def test_unparseable_fecha_sinks_without_crashing(self):
        nodes = [
            make_email_node("good@uchile.cl", "2022-01-01T00:00:00-03:00"),
            make_email_node("bad@uchile.cl", "not-a-date"),
        ]
        _, others = extract_and_split_emails(nodes)

        self.assertEqual(others, ["good@uchile.cl", "bad@uchile.cl"])

    def test_empty_list(self):
        principal, others = extract_and_split_emails([])
        self.assertEqual(principal, "")
        self.assertEqual(others, [])


class ProcessPersonaDataTests(SimpleTestCase):
    """test process_persona_data pydantic validation and email split."""

    def _raw_persona(self, **overrides):
        base = {
            "id_persona": 100,
            "nombres": "Nombre",
            "paterno": "Paterno",
            "materno": "Materno",
            "email": [
                make_raw_email("user@uchile.cl", "2021-01-01T00:00:00-03:00", principal=True),
                make_raw_email("user.alt@uchile.cl", "2022-01-01T00:00:00-03:00"),
            ],
        }
        base.update(overrides)
        return base

    def test_valid_persona_returns_clean_dict(self):
        result = process_persona_data([self._raw_persona()])

        self.assertEqual(result["id_persona"], 100)
        self.assertEqual(result["nombres"], "Nombre")
        self.assertEqual(result["paterno"], "Paterno")
        self.assertEqual(result["materno"], "Materno")
        self.assertEqual(result["email_principal"], "user@uchile.cl")
        self.assertEqual(result["emails"], ["user.alt@uchile.cl"])

    def test_empty_list_returns_empty_dict(self):
        self.assertEqual(process_persona_data([]), {})

    def test_validation_failure_returns_empty_dict(self):
        bad = self._raw_persona()
        del bad["id_persona"]
        self.assertEqual(process_persona_data([bad]), {})

    def test_only_first_record_processed(self):
        first = self._raw_persona(id_persona=1, nombres="First")
        second = self._raw_persona(id_persona=2, nombres="Second")
        result = process_persona_data([first, second])
        self.assertEqual(result["id_persona"], 1)


class SelectEmailForAccountTests(SimpleTestCase):
    """test select_email_for_account principal preference and validation fallback."""

    def test_valid_principal_chosen(self):
        self.assertEqual(
            select_email_for_account("main@uchile.cl", ["other@uchile.cl"]),
            "main@uchile.cl",
        )

    def test_invalid_principal_falls_back_to_first_valid(self):
        self.assertEqual(
            select_email_for_account("not-an-email", ["recent@uchile.cl", "mid@uchile.cl"]),
            "recent@uchile.cl",
        )

    def test_no_principal_uses_first_valid(self):
        self.assertEqual(
            select_email_for_account(None, ["bad", "ok@uchile.cl"]),
            "ok@uchile.cl",
        )

    def test_nothing_valid_raises(self):
        with self.assertRaises(NoValidEmailError):
            select_email_for_account(None, ["bad", "also-bad"])

    def test_empty_everything_raises(self):
        with self.assertRaises(NoValidEmailError):
            select_email_for_account(None, [])

class GenerateUsernameTests(TestCase):
    """utils.generate_username with the structured-keys input build_details uses."""

    def test_first_last_when_available(self):
        username = generate_username(
            {"nombres": "Juan", "apellidoPaterno": "Perez", "apellidoMaterno": "Soto"}
        )
        self.assertEqual(username, "Juan_Perez")

    def test_collision_progresses_to_next_strategy(self):
        User.objects.create_user("Juan_Perez", "taken@uchile.cl", "pass1234")
        username = generate_username(
            {"nombres": "Juan", "apellidoPaterno": "Perez", "apellidoMaterno": "Soto"}
        )
        self.assertNotEqual(username, "Juan_Perez")
        self.assertEqual(username, "Juan_Perez_S")


class FindExistingUserTests(TestCase):
    """user_creation.find_existing_user lookup and multi-match resolution."""

    def test_no_match_returns_none(self):
        self.assertIsNone(find_existing_user(["nobody@uchile.cl"], "nobody@uchile.cl"))

    def test_single_match_returned(self):
        u = User.objects.create_user("solo", "a@uchile.cl", "pass1234")
        self.assertEqual(find_existing_user(["a@uchile.cl"], "a@uchile.cl"), u)

    def test_multi_match_priority_email_wins(self):
        priority = User.objects.create_user("prio", "p@uchile.cl", "pass1234")
        User.objects.create_user("other", "a@uchile.cl", "pass1234")
        result = find_existing_user(["p@uchile.cl", "a@uchile.cl"], "p@uchile.cl")
        self.assertEqual(result, priority)

    def test_multi_match_falls_back_to_recent_last_login(self):
        old = User.objects.create_user("old", "a@uchile.cl", "pass1234")
        recent = User.objects.create_user("recent", "b@uchile.cl", "pass1234")
        old.last_login = timezone.now() - timedelta(days=30)
        old.save()
        recent.last_login = timezone.now()
        recent.save()

        # priority email matches neither, so last_login decides
        result = find_existing_user(["p@uchile.cl", "a@uchile.cl", "b@uchile.cl"], "p@uchile.cl")
        self.assertEqual(result, recent)

    def test_never_logged_in_loses_tiebreak(self):
        never_logged_user = User.objects.create_user("never", "a@uchile.cl", "pass1234")
        logged = User.objects.create_user("logged", "b@uchile.cl", "pass1234")
        logged.last_login = timezone.now()
        logged.save()

        result = find_existing_user(["a@uchile.cl", "b@uchile.cl"], "no-priority@uchile.cl")
        self.assertEqual(result, logged)


class SyncProfileTests(TestCase):
    """user_creation.link_indiv_id upsert UserIndivId."""

    def test_creates_record(self):
        u = User.objects.create_user("bob", "bob@uchile.cl", "pass1234")
        link_indiv_id(u, "111")
        self.assertTrue(
            UserIndivId.objects.filter(user=u, indiv_id="111").exists()
        )

    def test_updates_existing_record(self):
        u = User.objects.create_user("bob", "bob@uchile.cl", "pass1234")
        link_indiv_id(u, "111")
        link_indiv_id(u, "222")
        records = UserIndivId.objects.filter(user=u)
        self.assertEqual(records.count(), 1)
        self.assertEqual(records.first().indiv_id, "222")

@patch("eol_sso.user_creation.get_persona_by_indiv_id")
class ProvisionUserFromIndivIdTests(TestCase):
    """The full provisioning flow, with the external API mocked."""

    def test_new_user_created_and_activated(self, mock_api):
        mock_api.return_value = FAKE_PERSONA
        user, details = provision_user_from_indiv_id(INDIV_ID)

        self.assertTrue(user.is_active)
        self.assertEqual(user.email, "juan.perez@test.cl")
        self.assertEqual(details["id_persona"], 999)
        self.assertEqual(details["indiv_id"], INDIV_ID)
        self.assertTrue(details["username"])
        self.assertTrue(
            UserIndivId.objects.filter(user=user, indiv_id=INDIV_ID).exists()
        )

    def test_existing_user_matched_by_email_not_recreated(self, mock_api):
        mock_api.return_value = FAKE_PERSONA
        existing = User.objects.create_user(
            "jp", "juan.perez@test.cl", "pass1234"
        )
        before = User.objects.count()

        user, details = provision_user_from_indiv_id(INDIV_ID)

        self.assertEqual(user.pk, existing.pk)
        self.assertEqual(User.objects.count(), before)
        self.assertTrue(
            UserIndivId.objects.filter(user=existing, indiv_id=INDIV_ID).exists()
        )

    def test_psa_linked_user_just_syncs(self, mock_api):
        mock_api.return_value = FAKE_PERSONA
        linked = User.objects.create_user("m", "m@uchile.cl", "pass1234")
        before = User.objects.count()

        user, details = provision_user_from_indiv_id(INDIV_ID, existing_user=linked)

        self.assertEqual(user.pk, linked.pk)
        self.assertEqual(User.objects.count(), before)
        self.assertTrue(UserIndivId.objects.filter(user=linked).exists())

    def test_invalid_principal_falls_back_to_valid_email(self, mock_api):
        mock_api.return_value = {
            **FAKE_PERSONA,
            "email_principal": "not-an-email",
            "emails": ["also-bad", "fallback@valid.cl"],
        }
        user, _ = provision_user_from_indiv_id(INDIV_ID)
        self.assertEqual(user.email, "fallback@valid.cl")

    def test_no_persona_data_raises(self, mock_api):
        mock_api.return_value = {}
        with self.assertRaises(PersonaNotFoundError):
            provision_user_from_indiv_id(INDIV_ID)

    def test_no_valid_email_raises(self, mock_api):
        mock_api.return_value = {
            **FAKE_PERSONA,
            "email_principal": None,
            "emails": [],
        }
        with self.assertRaises(NoValidEmailError):
            provision_user_from_indiv_id(INDIV_ID)


@patch("eol_sso.user_creation.get_persona_by_indiv_id")
class ResolveUidTests(TestCase):
    """
    The resolve_uid pipeline step, tests fetches persona data, overrides uid with
    id_persona, stashes persona_data for downstream steps.
    """

    def setUp(self):
        self.backend = mock.Mock()
        self.backend.name = "uchile-oauth2"

    def test_overrides_uid_with_id_persona(self, mock_api):
        mock_api.return_value = FAKE_PERSONA

        result = resolve_uid(self.backend, {"identification": INDIV_ID})

        self.assertEqual(result["uid"], "999")

    def test_stashes_persona_data_for_downstream_steps(self, mock_api):
        mock_api.return_value = FAKE_PERSONA

        result = resolve_uid(self.backend, {"identification": INDIV_ID})

        self.assertEqual(result["persona_data"], FAKE_PERSONA)

    def test_missing_identification_raises_authforbidden(self, mock_api):
        with self.assertRaises(AuthForbidden):
            resolve_uid(self.backend, {})
        mock_api.assert_not_called()

    def test_empty_api_response_raises_authforbidden(self, mock_api):
        mock_api.return_value = {}

        with self.assertRaises(AuthForbidden):
            resolve_uid(self.backend, {"identification": INDIV_ID})


@patch("eol_sso.user_creation.get_persona_by_indiv_id")
class PipelineProvisionUserTests(TestCase):
    """
    The provision_user pipeline step.

    By the time this runs, resolve_uid has already stashed persona_data in
    kwargs and social_user has attempted to find an existing UserSocialAuth
    link.
    """

    def setUp(self):
        self.backend = mock.Mock()
        self.backend.name = "uchile-oauth2"

    def test_new_user_is_created_from_persona_data(self, mock_api):
        result = provision_user(
            self.backend,
            details={"identification": INDIV_ID},
            uid="999",
            persona_data=FAKE_PERSONA,
        )

        self.assertTrue(result["user"].is_active)
        self.assertEqual(result["user"].email, "juan.perez@test.cl")
        self.assertEqual(result["details"]["first_name"], "Juan Carlos")
        mock_api.assert_not_called()

    def test_existing_user_skips_provisioning_and_syncs_indiv_id(self, mock_api):
        linked = User.objects.create_user("m", "m@other.cl", "pass1234")

        result = provision_user(
            self.backend,
            details={"identification": INDIV_ID},
            uid="999",
            user=linked,
            persona_data=FAKE_PERSONA,
        )

        self.assertEqual(result["user"].pk, linked.pk)
        self.assertTrue(
            UserIndivId.objects.filter(user=linked, indiv_id=INDIV_ID).exists()
        )
        # Early-return path must not hit the API
        mock_api.assert_not_called()

    def test_provisioning_error_converted_to_authforbidden(self, mock_api):
        # No persona_data and no existing user falls through to
        # provision_user_from_indiv_id, which fetches and fails.
        mock_api.return_value = {}

        with self.assertRaises(AuthForbidden):
            provision_user(
                self.backend, {"identification": INDIV_ID}, uid="999"
            )


class BackendMethodTests(TestCase):
    """UchileOAuth2Backend method-level behavior."""

    def setUp(self):
        # Instantiate the backend directly with a Django strategy. The methods
        # being tested do not touch the network or storage.
        self.backend = UchileOAuth2Backend(strategy=load_strategy(), redirect_uri=None)

    def test_get_user_details_only_surfaces_identification(self):
        response = {
            "sub": "abc",
            "identification": "12.345.678-9",
            "preferred_username": "ignored",
            "email": "ignored@uchile.cl",
            "given_name": "Ignored",
            "family_name": "AlsoIgnored",
        }
        details = self.backend.get_user_details(response)
        self.assertEqual(details, {"identification": "12.345.678-9"})

    def test_get_user_id_returns_sub(self):
        self.assertEqual(self.backend.get_user_id({}, {"sub": "the-sub"}), "the-sub")

    def test_user_data_calls_userinfo_with_bearer_token(self):
        expected = {"sub": "abc", "identification": "123"}
        self.backend.get_json = mock.Mock(return_value=expected)

        result = self.backend.user_data("my-token")

        self.assertEqual(result, expected)
        self.backend.get_json.assert_called_once_with(
            self.backend.USER_DATA_URL,
            headers={"Authorization": "Bearer my-token"},
        )


@patch("eol_sso.user_creation.get_persona_by_indiv_id")
class BackendFullChainTests(TestCase):
    """
    End-to-end from a userinfo response to a provisioned, linked user.
    Simulates the full PSA pipeline order: backend extracts details, then
    resolve_uid runs, then provision_user runs.
    """

    def setUp(self):
        self.backend = UchileOAuth2Backend(strategy=load_strategy(), redirect_uri=None)

    def test_first_login_creates_user_and_keys_link_on_id_persona(self, mock_api):
        mock_api.return_value = FAKE_PERSONA

        # Backend processes the provider's userinfo response
        userinfo = {
            "sub": "provider-sub-1",
            "identification": INDIV_ID,
            "preferred_username": "should-be-ignored",
            "email": "should-be-ignored@uchile.cl",
        }
        details = self.backend.get_user_details(userinfo)
        uid = self.backend.get_user_id({}, userinfo)

        # resolve_uid overrides uid with id_persona and stashes persona_data
        resolved = resolve_uid(self.backend, details)
        self.assertEqual(resolved["uid"], "999")
        self.assertNotEqual(resolved["uid"], uid)

        # provision_user creates the account using the pre-fetched data.
        # With no existing UserSocialAuth link, social_user would have
        # left `user` unset — we simulate that by omitting the kwarg.
        result = provision_user(
            self.backend,
            details,
            uid=resolved["uid"],
            persona_data=resolved["persona_data"],
        )
        user = result["user"]

        # Account was created from external-API data, not the provider's userinfo
        self.assertTrue(user.is_active)
        self.assertEqual(user.email, "juan.perez@test.cl")
        # Identity link written and keyed on id_persona
        self.assertTrue(
            UserIndivId.objects.filter(user=user, indiv_id=INDIV_ID).exists()
        )
        # Only resolve_uid hit the API — provision_user reused the stashed data
        self.assertEqual(mock_api.call_count, 1)

    def test_returning_user_skips_provisioning(self, mock_api):
        """
        On subsequent logins, social_user finds the UserSocialAuth link by
        id_persona and populates user. provision_user should early-return
        with just a link_indiv_id call, no email matching, no creation since the
        user already exists.
        """
        mock_api.return_value = FAKE_PERSONA
        linked = User.objects.create_user("returning", "returning@test.cl", "pass1234")

        userinfo = {"sub": "provider-sub-1", "identification": INDIV_ID}
        details = self.backend.get_user_details(userinfo)
        resolved = resolve_uid(self.backend, details)

        result = provision_user(
            self.backend,
            details,
            uid=resolved["uid"],
            user=linked,
            persona_data=resolved["persona_data"],
        )

        self.assertEqual(result["user"].pk, linked.pk)
        self.assertTrue(
            UserIndivId.objects.filter(user=linked, indiv_id=INDIV_ID).exists()
        )
