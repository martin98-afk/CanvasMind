# -*- coding: utf-8 -*-
from enum import Enum

from qfluentwidgets import StyleSheetBase, Theme, qconfig

from app.utils.utils import resource_path


class StyleSheet(StyleSheetBase, Enum):
    """ Style sheet  """

    LINK_CARD = "link_card"
    SAMPLE_CARD = "sample_card"
    HOME_INTERFACE = "home_interface"
    COMPONENT_DEVELOPER = "component_developer"
    PACKAGE_MANAGER = "package_manager"
    CATEGORY_FILTER = "category_filter"

    def path(self, theme=Theme.AUTO):
        theme = qconfig.theme if theme == Theme.AUTO else theme
        return resource_path(f"resource/{self.value}.qss")
