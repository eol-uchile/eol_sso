#!/bin/bash

set -e

pip install pytest-cov genbadge[coverage]
pip install --src /openedx/venv/src -e /openedx/requirements/app

cd /openedx/requirements/app

# test uchileedxlogin
pip install --src /openedx/venv/src -e git+https://github.com/eol-uchile/uchileedxlogin@2.0.0#egg=uchileedxlogin
mkdir -p test_root
ln -s /openedx/staticfiles ./test_root/
DJANGO_SETTINGS_MODULE=lms.envs.test EDXAPP_TEST_MONGO_HOST=mongodb pytest -s -vvv --no-cov eol_sso/services/tests_uchileedxlogin.py eol_sso/tests.py

rm -rf test_root .coverage .coverage.xml
