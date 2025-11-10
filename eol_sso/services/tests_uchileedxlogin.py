# -*- coding: utf-8 -*-
# Python Standard Libraries
import logging

# Installed packages (via pip)
from django.test import TestCase
from mock import patch, MagicMock
from uchileedxlogin.services.interface import (
        PhApiException as UchileedxloginPhApiException,
        EmailException as UchileedxloginEmailException
    )

# Edx dependencies
from student.tests.factories import UserFactory

# Internal project dependencies
from eol_sso.services.interface import get_indiv_id, get_user_id_with_indiv_id_list, get_user_by_indiv_id, sso_user_factory, PhApiException, EmailException

logger = logging.getLogger(__name__)

class EolSsoInterfaceTests(TestCase):
    def setUp(self):
        # Patch the comment client user save method so it does not try
        # to create a new cc user when creating a django user
        with patch('student.models.cc.User.save'):
            self.user = UserFactory(username='student', email='student@edx.org')

    @patch('eol_sso.services.interface.uchileedxlogin_get_doc_id_by_user_id')
    def test_get_indiv_id_none_return_value(self, mock_doc_id):
        """
        Test get_indiv_id when uchileedxlogin get_doc_id returns None.
        """
        mock_doc_id.return_value = None
        indiv_id = get_indiv_id(self.user.id)
        self.assertEqual(indiv_id, None)

    @patch('eol_sso.services.interface.uchileedxlogin_get_doc_id_by_user_id')
    def test_get_indiv_id_passport_return_value(self, mock_doc_id):
        """
        Test get_indiv_id when uchileedxlogin get_doc_id returns a passport.
        """
        mock_doc_id.return_value = 'P1234567'
        indiv_id = get_indiv_id(self.user.id)
        self.assertEqual(indiv_id, 'P1234567')

    @patch('eol_sso.services.interface.uchileedxlogin_get_user_id_doc_id_pairs')
    def test_get_user_id_with_doc_empty_list_return_value(self, mock_doc_id):
        """
        Test get_user_id_with_doc_list when the return value of uchileedxlogin
        get_user_id_doc_id_pairs is an empty list.
        """
        mock_doc_id.return_value = []
        user_id_indiv_id_tuples_list = get_user_id_with_indiv_id_list([self.user.id])
        self.assertEqual(user_id_indiv_id_tuples_list, [])

    @patch('eol_sso.services.interface.uchileedxlogin_get_user_id_doc_id_pairs')
    def test_get_user_id_with_doc_pair_return_value(self, mock_doc_id):
        """
        Test get_user_id_with_doc_list when the return value of uchileedxlogin
        get_user_id_doc_id_pairs has a pair of values.
        """
        mock_doc_id.return_value = [(self.user.id, '1234568')]
        user_id_indiv_id_tuples_list = get_user_id_with_indiv_id_list([self.user.id])
        self.assertEqual(user_id_indiv_id_tuples_list, [(self.user.id, '1234568')])

    @patch('eol_sso.services.interface.uchileedxlogin_get_user_by_doc_id')
    def test_get_user_by_indiv_id_none_return_value(self, mock_user):
        """
        Test get_user_by_indiv_id when the return value of uchileedxlogin 
        get_user_by_doc_id is None.
        """
        mock_user.return_value = None
        user = get_user_by_indiv_id('123456789')
        self.assertEqual(user, None)

    @patch('eol_sso.services.interface.uchileedxlogin_get_user_by_doc_id')
    def test_get_user_by_indiv_id_user_return_value(self, mock_user):
        """
        Test get_user_by_indiv_id when the return value of uchileedxlogin 
        get_user_by_doc_id is a user.
        """
        mock_edxloginuser = MagicMock()
        mock_edxloginuser.user = self.user
        mock_edxloginuser.rut = '123456789'

        mock_user.return_value = mock_edxloginuser
        user = get_user_by_indiv_id('123456789')
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
