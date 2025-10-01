from django.apps import AppConfig
from openedx.core.djangoapps.plugins.constants import (
    PluginURLs,
    ProjectType,
)


class EolSsoConfig(AppConfig):
    name = 'eol_sso'
    plugin_app = {
        PluginURLs.CONFIG: {
            ProjectType.LMS: {
                PluginURLs.NAMESPACE: "eol-sso",
                PluginURLs.REGEX: r"",
                PluginURLs.RELATIVE_PATH: "urls",
            }},
    }
