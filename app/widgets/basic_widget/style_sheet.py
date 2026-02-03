# -*- coding: utf-8 -*-
from enum import Enum

from qfluentwidgets import StyleSheetBase, Theme, qconfig

from app.utils.utils import resource_path


class StyleSheet(StyleSheetBase, Enum):
    """ Style sheet  """

    VARIABLE_EXPLORER = "variable_explorer"
    LINK_CARD = "link_card"
    SAMPLE_CARD = "sample_card"
    HOME_INTERFACE = "home_interface"
    PACKAGE_MANAGER = "package_manager"
    CATEGORY_FILTER = "category_filter"
    FIND_REPLACE = "find_replace"
    CODE_EDITOR = "code_editor"
    COMPONENT_MARKET = "component_market"
    RANGE_WIDGET = "range_widget"
    QLIST = "qlist"

    def path(self, theme=Theme.AUTO):
        return resource_path(f"resource/{self.value}.qss")
