# -*- coding: utf-8 -*-
# Python Standard Libraries
import logging

# Installed packages (via pip)
from django.contrib.auth.models import User
from django.test import TestCase
from mock import patch
from eol_sso_login.models import SSOLoginExtraData

# Edx dependencies
from student.tests.factories import UserFactory

# Internal project dependencies
from eol_sso.services.interface import get_indiv_id, get_user_by_indiv_id, get_user_id_with_indiv_id_list

logger = logging.getLogger(__name__)


class EolSsoInterfaceTests(TestCase):

    def setUp(self):
        # Patch the comment client user save method so it does not try
        # to create a new cc user when creating a django user
        with patch('student.models.cc.User.save'):
            self.user = UserFactory(username='student', email='student@edx.org')

    @patch('eol_sso.services.interface.SSOLoginExtraData.objects')
    def test_get_indiv_id_none_return_value(self, mock_get):
        """
        Test get_indiv_id when the user doesn't have extra data
        """
        mock_get.values_list.return_value.get.side_effect = SSOLoginExtraData.DoesNotExist
        indiv_id = get_indiv_id(self.user.id)
        self.assertEqual(indiv_id, None)

    @patch('eol_sso.services.interface.SSOLoginExtraData.objects')
    def test_get_indiv_id_rut(self, mock_get):
        """
        Test get_indiv_id when the user has a indiv_id
        """
        mock_get.values_list.return_value.get.return_value = '12345678'
        indiv_id = get_indiv_id(self.user.id)
        self.assertEqual(indiv_id, '12345678')

    @patch('eol_sso.services.interface.SSOLoginExtraData.objects')
    def test_get_indiv_id_passport(self, mock_get):
        """
        Test get_indiv_id when the user has a indiv_id following the passport format
        """
        mock_get.values_list.return_value.get.return_value = 'P2345678'
        indiv_id = get_indiv_id(self.user.id)
        self.assertEqual(indiv_id, 'P2345678')

    @patch('eol_sso.services.interface.SSOLoginExtraData.objects')
    def test_get_user_id_with_indiv_id_list_empty_list_return_value(self, mock_user_doc_id_queryset):
        """
        Test get_user_id_with_indiv_id_list when the user doesn't have extra data
        """
        mock_user_doc_id_queryset.filter.return_value.values_list.return_value = []
        user_id_doc_tuples_list = get_user_id_with_indiv_id_list([self.user.id])
        self.assertEqual(user_id_doc_tuples_list, [])

    @patch('eol_sso.services.interface.SSOLoginExtraData.objects')
    def test_get_user_id_with_indiv_id_list(self, mock_user_doc_id_queryset):
        """
        Test get_user_id_with_indiv_id_list when the user has extra data
        """
        mock_user_doc_id_queryset.filter.return_value.values_list.return_value = [(self.user.id, '1234568')]
        user_id_doc_tuples_list = get_user_id_with_indiv_id_list([self.user.id])
        self.assertEqual(user_id_doc_tuples_list, [(self.user.id, '1234568')])

    @patch('eol_sso.services.interface.User.objects.get')
    def test_get_user_by_indiv_id_none_return_value(self, mock_user):
        """
        Test get_user_by_indiv_id when the indiv_id is not linked to any users
        """
        mock_user.side_effect = User.DoesNotExist
        user = get_user_by_indiv_id('123456789')
        self.assertEqual(user, None)

    @patch('eol_sso.services.interface.User.objects.get')
    def test_get_user_by_indiv_id_user_return_value(self, mock_response):
        """
        Test get_user_by_indiv_id when the indiv_id is linked to a user
        """
        mock_response.return_value = self.user
        user = get_user_by_indiv_id('P123456789')
        self.assertEqual(user, self.user)
