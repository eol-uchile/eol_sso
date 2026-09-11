# -*- coding: utf-8 -*-
# Python Standard Libraries
import logging
from unittest import mock

# Installed packages (via pip)
from django.contrib.auth.models import User
from django.test import TestCase
from mock import patch

# Edx dependencies
from student.tests.factories import UserFactory

# Internal project dependencies
from eol_sso.exceptions import PersonaNotFoundError, NoValidEmailError
from eol_sso.models import UserIndivId
from eol_sso.services.interface import (
    get_indiv_id,
    get_user_id_with_indiv_id_list,
    get_user_by_indiv_id,
    sso_user_factory,
    PhApiException,
    EmailException,
)

logger = logging.getLogger(__name__)


class EolSsoInterfaceTests(TestCase):
    """
    Tests interface.py's dispatch to the eol_sso/UserIndivId model
    """

    def setUp(self):
        # Patch the comment client user save method so it does not try
        # to create a new cc user when creating a django user
        with patch('student.models.cc.User.save'):
            self.user = UserFactory(username='student', email='student@edx.org')

    @patch('eol_sso.services.interface.MODEL_USED', 'eol_sso')
    @patch('eol_sso.services.interface.UserIndivId.objects')
    def test_get_indiv_id_none_return_value(self, mock_get):
        """
        Test get_indiv_id when the user has no UserIndivId record.
        """
        mock_get.values_list.return_value.get.side_effect = UserIndivId.DoesNotExist
        indiv_id = get_indiv_id(self.user.id)
        self.assertEqual(indiv_id, None)

    @patch('eol_sso.services.interface.MODEL_USED', 'eol_sso')
    @patch('eol_sso.services.interface.UserIndivId.objects')
    def test_get_indiv_id_rut(self, mock_get):
        """
        Test get_indiv_id when the user has a rut-format indiv_id.
        """
        mock_get.values_list.return_value.get.return_value = '12345678'
        indiv_id = get_indiv_id(self.user.id)
        self.assertEqual(indiv_id, '12345678')

    @patch('eol_sso.services.interface.MODEL_USED', 'eol_sso')
    @patch('eol_sso.services.interface.UserIndivId.objects')
    def test_get_indiv_id_passport(self, mock_get):
        """
        Test get_indiv_id when the user has a passport-format indiv_id.
        """
        mock_get.values_list.return_value.get.return_value = 'P2345678'
        indiv_id = get_indiv_id(self.user.id)
        self.assertEqual(indiv_id, 'P2345678')

    @patch('eol_sso.services.interface.MODEL_USED', 'eol_sso')
    @patch('eol_sso.services.interface.UserIndivId.objects')
    def test_get_user_id_with_indiv_id_list_empty_list_return_value(self, mock_queryset):
        """
        Test get_user_id_with_indiv_id_list when no users have a UserIndivId record.
        """
        mock_queryset.filter.return_value.values_list.return_value = []
        user_id_indiv_id_tuples_list = get_user_id_with_indiv_id_list([self.user.id])
        self.assertEqual(user_id_indiv_id_tuples_list, [])

    @patch('eol_sso.services.interface.MODEL_USED', 'eol_sso')
    @patch('eol_sso.services.interface.UserIndivId.objects')
    def test_get_user_id_with_indiv_id_list(self, mock_queryset):
        """
        Test get_user_id_with_indiv_id_list when a user has a UserIndivId record.
        """
        mock_queryset.filter.return_value.values_list.return_value = [(self.user.id, '1234568')]
        user_id_indiv_id_tuples_list = get_user_id_with_indiv_id_list([self.user.id])
        self.assertEqual(user_id_indiv_id_tuples_list, [(self.user.id, '1234568')])

    @patch('eol_sso.services.interface.MODEL_USED', 'eol_sso')
    @patch('eol_sso.services.interface.User.objects.get')
    def test_get_user_by_indiv_id_none_return_value(self, mock_user):
        """
        Test get_user_by_indiv_id when the indiv_id is not linked to any user.
        """
        mock_user.side_effect = User.DoesNotExist
        user = get_user_by_indiv_id('123456789')
        self.assertEqual(user, None)

    @patch('eol_sso.services.interface.MODEL_USED', 'eol_sso')
    @patch('eol_sso.services.interface.User.objects.get')
    def test_get_user_by_indiv_id_user_return_value(self, mock_response):
        """
        Test get_user_by_indiv_id when the indiv_id is linked to a user.
        """
        mock_response.return_value = self.user
        user = get_user_by_indiv_id('P123456789')
        self.assertEqual(user, self.user)

    @patch('eol_sso.services.interface.MODEL_USED', 'eol_sso')
    @patch('eol_sso.services.interface.create_social_auth_entry')
    @patch('eol_sso.services.interface.provision_user_from_indiv_id')
    def test_sso_user_factory_eol_sso_success(self, mock_provision, mock_create_social_auth):
        """
        Test sso_user_factory (eol_sso branch) provisions the user and
        returns the created UserSocialAuth entry.
        """
        fake_user_data = {"id_persona": 999}
        mock_provision.return_value = (self.user, fake_user_data)
        fake_social_auth = mock.Mock()
        mock_create_social_auth.return_value = fake_social_auth

        result = sso_user_factory('12345678', 'doc_id')

        mock_provision.assert_called_once_with('12345678')
        mock_create_social_auth.assert_called_once_with(self.user, fake_user_data)
        self.assertEqual(result, fake_social_auth)

    @patch('eol_sso.services.interface.MODEL_USED', 'eol_sso')
    @patch('eol_sso.services.interface.provision_user_from_indiv_id')
    def test_sso_user_factory_eol_sso_invalid_value_type(self, mock_provision):
        """
        Test sso_user_factory (eol_sso branch) returns None and never
        provisions anything for an unsupported value_type.
        """
        result = sso_user_factory('12345678', 'usuario')

        self.assertIsNone(result)
        mock_provision.assert_not_called()

    @patch('eol_sso.services.interface.MODEL_USED', 'eol_sso')
    @patch('eol_sso.services.interface.provision_user_from_indiv_id')
    def test_sso_user_factory_eol_sso_persona_not_found(self, mock_provision):
        """
        Test sso_user_factory (eol_sso branch) translates PersonaNotFoundError
        into the shared PhApiException.
        """
        mock_provision.side_effect = PersonaNotFoundError()
        with self.assertRaises(PhApiException):
            sso_user_factory('12345678', 'doc_id')

    @patch('eol_sso.services.interface.MODEL_USED', 'eol_sso')
    @patch('eol_sso.services.interface.provision_user_from_indiv_id')
    def test_sso_user_factory_eol_sso_no_valid_email(self, mock_provision):
        """
        Test sso_user_factory (eol_sso branch) translates NoValidEmailError
        into the shared EmailException.
        """
        mock_provision.side_effect = NoValidEmailError()
        with self.assertRaises(EmailException):
            sso_user_factory('12345678', 'doc_id')

    @patch('eol_sso.services.interface.MODEL_USED', 'eol_sso_login')
    def test_sso_user_factory_eol_sso_login_not_implemented(self):
        """
        Test sso_user_factory raises NotImplementedError for the
        eol_sso_login branch, matching its documented contract.
        """
        with self.assertRaises(NotImplementedError):
            sso_user_factory('12345678', 'doc_id')
