# -*- coding: utf-8 -*-
# Python Standard Libraries
import logging

# Installed packages (via pip)
from django.test import TestCase
from mock import Mock, patch
from eol_sso_login.models import SSOLoginExtraData

# Edx dependencies
from student.tests.factories import UserFactory

# Internal project dependencies
from eol_sso.services.interface import get_document_type, get_doc_id_by_user_id, get_user_id_doc_id_pairs

logger = logging.getLogger(__name__)


class EolSsoInterfaceTests(TestCase):

    def setUp(self):
        # Patch the comment client user save method so it does not try
        # to create a new cc user when creating a django user
        with patch('student.models.cc.User.save'):
            self.user = UserFactory(username='student', email='student@edx.org')
            self.user2 = UserFactory(username='student2', email='student2@edx.org')

    @patch('eol_sso.services.interface.SSOLoginExtraData.objects')
    def test_get_doc_id_by_user_id_none_return_value(self, mock_get):
        """
        Test get_doc_id_by_user_id when the user doesn't have extra data
        """
        mock_get.values_list.return_value.get.side_effect = SSOLoginExtraData.DoesNotExist
        doc_id = get_doc_id_by_user_id(self.user.id)
        self.assertEqual(doc_id, None)

    @patch('eol_sso.services.interface.SSOLoginExtraData.objects')
    def test_get_doc_id_by_user_id_doc_id_return_value(self, mock_get):
        """
        Test get_doc_id_by_user_id when the user has extra data
        """
        mock_get.values_list.return_value.get.return_value = 12345678
        doc_id = get_doc_id_by_user_id(self.user.id)
        self.assertEqual(doc_id, 12345678)

    @patch('eol_sso.services.interface.SSOLoginExtraData.objects')
    def test_get_user_id_doc_id_pairs_empty_list_return_value(self, mock_user_doc_id_pair):
        """
        Test get_user_id_doc_id_pairs when the user doesn't have extra data
        """
        mock_user_doc_id_pair.filter.return_value.values_list.return_value = []
        user_id_doc_id_list = get_user_id_doc_id_pairs([self.user.id])
        self.assertEqual(user_id_doc_id_list, [])

    @patch('eol_sso.services.interface.SSOLoginExtraData.objects')
    def test_get_user_id_doc_id_pairs_pair_return_value(self, mock_user_doc_id_pair):
        """
        Test get_user_id_doc_id_pairs when the user has extra data
        """
        mock_user_doc_id_pair.filter.return_value.values_list.return_value = [(self.user.id, 1234568)]
        user_id_doc_id_list = get_user_id_doc_id_pairs([self.user.id])
        self.assertEqual(user_id_doc_id_list, [(self.user.id, 1234568)])

    @patch('eol_sso.services.interface.SSOLoginExtraData.objects')
    def test_get_document_type_extra_data(self, mock_get):
        """
        Test get_document_type when the user has extra data
        """
        mock_query_response = Mock()
        mock_query_response.type_document = 'run'
        mock_get.get.return_value = mock_query_response
        document_type = get_document_type(12346787)
        self.assertEqual(document_type, 'run')

    @patch('eol_sso.services.interface.SSOLoginExtraData.objects')
    def test_get_document_type_none_return_value(self, mock_get):
        """
        Test get_doc_id_by_user_id when the user doesn't have extra data
        """
        mock_get.get.side_effect = SSOLoginExtraData.DoesNotExist
        document_type = get_document_type(12346787)
        self.assertEqual(document_type, None)
