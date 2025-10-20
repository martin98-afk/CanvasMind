import uuid
from NodeGraphQt import NodeObject


class BasicNodeWithGlobalProperty(NodeObject):
    """
    所有业务节点的基类
    """

    def __init__(self, qgraphics_item=None):
        super().__init__(qgraphics_item)
        self.model.add_property("global_variable", {})
        self.model.add_property("persistent_id", str(uuid.uuid4()))