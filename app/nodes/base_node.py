from NodeGraphQt import NodeObject


class BasicNodeWithGlobalProperty(NodeObject):

    def __init__(self, qgraphics_item=None):
        super().__init__(qgraphics_item)
        self.model.add_property("global_variable", {})