from NodeGraphQt import BaseNode, NodeBaseWidget
from Qt import QtWidgets


class TemplatePlotWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__()
        from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
        from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
        import matplotlib.pyplot as plt
        highlightColor = str('white')
        self.setFixedSize(600, 400)
        self.mainLayout = QtWidgets.QVBoxLayout(self)   
        self.mainLayout.setSpacing(10)
        self.figure = plt.figure(facecolor=highlightColor)
        self.canvas = FigureCanvas(self.figure)
        
        self.toolbar = NavigationToolbar(self.canvas, self)
        self.mainLayout.addWidget(self.canvas)
        self.mainLayout.addWidget(self.toolbar)
    
        
class TemplatePlotWidgetWrapper(NodeBaseWidget):
    def __init__(self, parent=None, fretData=None):
        super().__init__(parent)
        self.plot_widget = TemplatePlotWidget(parent=parent)
        self.set_custom_widget(self.plot_widget)
        self.fretData=fretData
    
        self.plot_widget.figure.clf()

    def get_value(self):
        return self.fretData
    
    def set_value(self, fretData):
        self.fretData = fretData