# -*- coding: utf-8 -*-
# Python Standard Libraries
import logging

# Installed packages (via pip)
from django.test import TestCase
from mock import patch
from uchileedxlogin.services.interface import (
        PhApiException as UchileedxloginPhApiException,
        EmailException as UchileedxloginEmailException
    )

# Edx dependencies
from student.tests.factories import UserFactory

# Internal project dependencies
from eol_sso.services.interface import get_doc_id_by_user_id, get_document_type, get_user_id_doc_id_pairs, get_user_by_doc_id, sso_user_factory, PhApiException, EmailException

logger = logging.getLogger(__name__)

class EolSsoInterfaceTests(TestCase):

    def setUp(self):
        # Patch the comment client user save method so it does not try
        # to create a new cc user when creating a django user
        with patch('student.models.cc.User.save'):
            self.user = UserFactory(username='student', email='student@edx.org')

    @patch('eol_sso.services.interface.uchileedxlogin_get_doc_id_by_user_id')
    def test_get_doc_id_by_user_id_none_return_value(self, mock_doc_id):
        """
        Test get_doc_id_by_user_id when uchileedxlogin get_doc_id_by_user_id returns None.
        """
        mock_doc_id.return_value = None
        doc_id = get_doc_id_by_user_id(self.user.id)
        self.assertEqual(doc_id, None)

    @patch('eol_sso.services.interface.uchileedxlogin_get_doc_id_by_user_id')
    def test_get_doc_id_by_user_id_doc_id_return_value(self, mock_doc_id):
        """
        Test get_doc_id_by_user_id when uchileedxlogin get_doc_id_by_user_id returns a doc_id.
        """
        mock_doc_id.return_value = 12345678
        doc_id = get_doc_id_by_user_id(self.user.id)
        self.assertEqual(doc_id, 12345678)

    @patch('eol_sso.services.interface.uchileedxlogin_get_user_id_doc_id_pairs')
    def test_get_user_id_doc_id_pairs_empty_list_return_value(self, mock_doc_id):
        """
        Test get_user_id_doc_id_pairs when the return value of uchileedxlogin 
        get_user_id_doc_id_pairs is an empty list.
        """
        mock_doc_id.return_value = []
        user_id_doc_id_list = get_user_id_doc_id_pairs([self.user.id])
        self.assertEqual(user_id_doc_id_list, [])

    @patch('eol_sso.services.interface.uchileedxlogin_get_user_id_doc_id_pairs')
    def test_get_user_id_doc_id_pairs_pair_return_value(self, mock_doc_id):
        """
        Test get_user_id_doc_id_pairs when the return value of uchileedxlogin
        get_user_id_doc_id_pairs has a pair of values.
        """
        mock_doc_id.return_value = [(self.user.id, 1234568)]
        user_id_doc_id_list = get_user_id_doc_id_pairs([self.user.id])
        self.assertEqual(user_id_doc_id_list, [(self.user.id, 1234568)])

    @patch('eol_sso.services.interface.uchileedxlogin_get_user_by_doc_id')
    def test_get_user_by_doc_id_none_return_value(self, mock_user):
        """
        Test get_user_by_doc_id when the return value of uchileedxlogin 
        get_user_by_doc_id is None.
        """
        mock_user.return_value = None
        user = get_user_by_doc_id(self.user.id, None)
        self.assertEqual(user, None)

    @patch('eol_sso.services.interface.uchileedxlogin_get_user_by_doc_id')
    def test_get_user_by_doc_id_user_return_value(self, mock_user):
        """
        Test get_user_by_doc_id when the return value of uchileedxlogin 
        get_user_by_doc_id is a user.
        """
        mock_user.return_value = self.user
        user = get_user_by_doc_id(123456789, 'rut')
        self.assertEqual(self.user, user)

    @patch('eol_sso.services.interface.uchileedxlogin_edxloginuser_factory')
    def test_sso_user_factory_user_return_value(self, mock_edxloginuser):
        """
        Test sso_user_factory when the return value of uchileedxlogin 
        edxloginuser_factory is a user.
        """
        mock_edxloginuser.return_value = self.user
        user = sso_user_factory(123456789, 'doc_id')
        self.assertEqual(self.user, user)

    @patch('eol_sso.services.interface.uchileedxlogin_edxloginuser_factory')
    def test_sso_user_factory_ph_api_exception(self, mock_edxloginuser):
        """
        Test sso_user_factory when a PhApiException is raised.
        """
        mock_edxloginuser.side_effect = UchileedxloginPhApiException()
        with self.assertRaises(PhApiException):
            sso_user_factory(123456789, 'doc_id')
    
    @patch('eol_sso.services.interface.uchileedxlogin_edxloginuser_factory')
    def test_sso_user_factory_email_exception(self, mock_edxloginuser):
        """
        Test sso_user_factory when an EmailException is raised.
        """
        mock_edxloginuser.side_effect = UchileedxloginEmailException()
        with self.assertRaises(EmailException):
            sso_user_factory(123456789, 'doc_id')

    @patch('eol_sso.services.interface.uchileedxlogin_get_document_type')
    def test_get_document_type(self, mock_get):
        """
        Test get_document_type for some document_id
        """
        mock_get.return_value = 'run'
        document_type = get_document_type(12346787)
        self.assertEqual(document_type, 'run')
