# -*- coding: utf-8 -*-
# Standard library imports
import sys
from typing import Optional, Dict

# Third party imports
import pandas as pd
from PyQt5.QtWidgets import QScrollBar, QTableView, QTableWidget, QItemDelegate
from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QVBoxLayout,
    QWidget,
    QFrame
)
from spyder.plugins.variableexplorer.widgets.dataframeeditor import DEFAULT_FORMAT, EmptyDataFrame, DataFrameModel, \
    DataFrameView, DataFrameLevelModel, DataFrameHeaderModel


# Import necessary components from the provided Spyder code
# Ensure the provided code is available in your Python path or in the same file
# For this example, we assume the code from the text file is in a module named `spyder_df_editor`
# You might need to adjust the import based on your actual file structure.
# For direct inclusion, we'll reference the classes assuming they are accessible in the global scope
# of the script where this class is defined.
# If they are in a separate file `spyder_df_editor.py`, uncomment the import line below:
# from spyder_df_editor import DataFrameModel, DataFrameView, DataFrameHeaderModel, DataFrameLevelModel, EmptyDataFrame

# --- IMPORTANT: Import Classes ---
# The following assumes that the classes DataFrameModel, DataFrameView,
# DataFrameHeaderModel, DataFrameLevelModel, EmptyDataFrame, and related
# constants (LARGE_SIZE, ROWS_TO_LOAD, COLS_TO_LOAD, etc.) are available
# in the scope where this ExcelViewer class is defined.
# If the provided code is in a file named `spyder_df_editor.py`, add:
# from spyder_df_editor import (
#     DataFrameModel, DataFrameView, DataFrameHeaderModel, DataFrameLevelModel, EmptyDataFrame,
#     LARGE_SIZE, ROWS_TO_LOAD, COLS_TO_LOAD, DEFAULT_FORMAT
# )
# Or, if the code is pasted directly before this class definition in the same file,
# no import is needed as they will be in the same scope.

# --- ExcelViewer Class ---
class ExcelViewer(QDialog):
    """
    Dialog for displaying Excel files with multiple sheets.

    Uses Spyder's DataFrame editor components to display each sheet.
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        readonly: bool = True, # Default to readonly for viewing
        format_spec: str = DEFAULT_FORMAT, # Default float format
    ):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.readonly = readonly
        self.format_spec = format_spec

        # Data storage
        self.excel_data: Dict[str, pd.DataFrame] = {}
        self.current_sheet_name: Optional[str] = None

        # UI Components
        self.sheet_combo: QComboBox = QComboBox()
        self.sheet_combo.currentTextChanged.connect(self._on_sheet_changed)
        self.sheet_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)

        self.status_label: QLabel = QLabel("Ready")
        self.progress_bar: QProgressBar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 0) # Indeterminate

        # Main view components (similar to DataFrameEditor)
        self.glayout = QGridLayout()
        self.glayout.setSpacing(0)
        self.glayout.setContentsMargins(0, 0, 0, 0)

        self.hscroll = QScrollBar(Qt.Horizontal)
        self.vscroll = QScrollBar(Qt.Vertical)

        # Create the view for the level
        self.create_table_level()
        # Create the view for the horizontal header
        self.create_table_header()
        # Create the view for the vertical index
        self.create_table_index()
        # Create the model and view for the data
        empty_data = EmptyDataFrame()
        self.dataModel = DataFrameModel(
            empty_data,
            format_spec=self.format_spec,
            parent=self,
            readonly=self.readonly
        )
        self.create_data_table()

        self.glayout.addWidget(self.hscroll, 2, 0, 1, 2)
        self.glayout.addWidget(self.vscroll, 0, 2, 2, 1)

        # Layout
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Sheet:"))
        top_layout.addWidget(self.sheet_combo)
        top_layout.addStretch()
        top_layout.addWidget(self.status_label)
        top_layout.addWidget(self.progress_bar)

        main_layout = QVBoxLayout()
        main_layout.addLayout(top_layout)
        main_layout.addLayout(self.glayout)
        main_layout.setSpacing(2)
        main_layout.setContentsMargins(2, 2, 2, 2)
        self.setLayout(main_layout)

        self.setWindowTitle("Excel Viewer")
        self.resize(800, 600) # Default size

    def setup_and_check(self, file_path: str) -> bool:
        """
        Load the Excel file and populate the sheet selector.

        Args:
            file_path: Path to the Excel file.

        Returns:
            True if successful, False otherwise.
        """
        self.status_label.setText("Loading...")
        self.progress_bar.setVisible(True)
        QApplication.processEvents() # Allow UI to update

        try:
            # Read all sheets
            self.excel_data = pd.read_excel(file_path, sheet_name=None)
            sheet_names = list(self.excel_data.keys())

            if not sheet_names:
                QMessageBox.warning(self, "Warning", "No sheets found in the Excel file.")
                return False

            self.sheet_combo.clear()
            self.sheet_combo.addItems(sheet_names)

            # Load the first sheet
            first_sheet_name = sheet_names[0]
            self._load_sheet(first_sheet_name)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load Excel file:\n{str(e)}")
            return False
        finally:
            self.status_label.setText("Ready")
            self.progress_bar.setVisible(False)

        return True

    def _on_sheet_changed(self, sheet_name: str):
        """Handle sheet selection change."""
        if sheet_name and sheet_name != self.current_sheet_name:
            self._load_sheet(sheet_name)

    def _load_sheet(self, sheet_name: str):
        """
        Load and display the specified sheet.

        Args:
            sheet_name: Name of the sheet to load.
        """
        if sheet_name not in self.excel_data:
            return

        self.status_label.setText(f"Loading {sheet_name}...")
        self.progress_bar.setVisible(True)
        QApplication.processEvents() # Allow UI to update

        try:
            df = self.excel_data[sheet_name]
            # Create a new model for the new DataFrame
            new_model = DataFrameModel(
                df,
                format_spec=self.format_spec,
                parent=self,
                readonly=self.readonly
            )
            # Update the view with the new model
            self.setModel(new_model)
            self.current_sheet_name = sheet_name
            self.setWindowTitle(f"Excel Viewer - {sheet_name}")
            self.status_label.setText(f"Showing: {sheet_name}")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load sheet '{sheet_name}':\n{str(e)}")
            self.status_label.setText("Error loading sheet")
        finally:
            self.progress_bar.setVisible(False)

    # --- Methods to replicate DataFrameEditor setup ---
    def create_table_level(self):
        """Create the QTableView for levels (top-left corner)."""
        self.table_level = QTableView()
        self.table_level.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_level.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table_level.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table_level.setFrameStyle(QFrame.Plain)
        self.table_level.setContentsMargins(0, 0, 0, 0)
        self.glayout.addWidget(self.table_level, 0, 0)

    def create_table_header(self):
        """Create the QTableView for column headers."""
        self.table_header = QTableView()
        self.table_header.verticalHeader().hide()
        self.table_header.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_header.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table_header.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table_header.setHorizontalScrollMode(QTableView.ScrollPerPixel)
        self.table_header.setHorizontalScrollBar(self.hscroll)
        self.table_header.setFrameStyle(QFrame.Plain)
        self.table_header.setItemDelegate(QItemDelegate())
        self.glayout.addWidget(self.table_header, 0, 1)

    def create_table_index(self):
        """Create the QTableView for row indices."""
        self.table_index = QTableView()
        self.table_index.horizontalHeader().hide()
        self.table_index.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_index.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table_index.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table_index.setVerticalScrollMode(QTableView.ScrollPerPixel)
        self.table_index.setVerticalScrollBar(self.vscroll)
        self.table_index.setFrameStyle(QFrame.Plain)
        self.table_index.setItemDelegate(QItemDelegate())
        self.glayout.addWidget(self.table_index, 1, 0)
        self.table_index.setContentsMargins(0, 0, 0, 0)

    def create_data_table(self):
        """Create the main QTableView for data, using DataFrameView."""
        self.dataTable = DataFrameView(
            self,
            self.dataModel,
            self.table_header.horizontalHeader(),
            self.hscroll,
            self.vscroll,
            namespacebrowser=None, # Assuming not needed for viewing
            data_function=None,    # Assuming not needed for viewing
            readonly=self.readonly
        )
        self.dataTable.verticalHeader().hide()
        self.dataTable.horizontalHeader().hide()
        self.dataTable.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.dataTable.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.dataTable.setHorizontalScrollMode(QTableView.ScrollPerPixel)
        self.dataTable.setVerticalScrollMode(QTableView.ScrollPerPixel)
        self.dataTable.setFrameStyle(QFrame.Plain)
        self.dataTable.setItemDelegate(QItemDelegate())
        self.glayout.addWidget(self.dataTable, 1, 1)
        self.setFocusProxy(self.dataTable)

    def setModel(self, model: DataFrameModel):
        """
        Set the model for all associated views (data, header, index, level).
        """
        self.dataModel = model # Store the new model reference
        self.dataTable.setModel(model)

        # Update associated models
        self._reset_model(self.table_level, DataFrameLevelModel(model))
        self._reset_model(self.table_header, DataFrameHeaderModel(model, 0))
        # Use monospace font for index to match data
        self._reset_model(
            self.table_index,
            DataFrameHeaderModel(model, 1, use_monospace_font=True)
        )

        # Update layout based on new model dimensions
        self._update_layout()

    def _reset_model(self, table, model):
        """Helper to set a model on a table, deleting the old selection model."""
        old_sel_model = table.selectionModel()
        table.setModel(model)
        if old_sel_model:
            del old_sel_model

    def _update_layout(self):
        """Set the width and height of the QTableViews based on content."""
        if not self.dataModel:
            return

        # Sync vertical header width for level and index
        h_width = max(
            self.table_level.verticalHeader().sizeHint().width(),
            self.table_index.verticalHeader().sizeHint().width()
        )
        self.table_level.verticalHeader().setFixedWidth(h_width)
        self.table_index.verticalHeader().setFixedWidth(h_width)

        # Sync horizontal header height for level and header
        last_row = self.dataModel.header_shape[0] - 1
        if last_row < 0:
            hdr_height = self.table_level.horizontalHeader().height()
        else:
            hdr_height = (self.table_level.rowViewportPosition(last_row) +
                          self.table_level.rowHeight(last_row) +
                          self.table_level.horizontalHeader().height())
            if last_row == 0:
                self.table_level.setRowHidden(0, True)
                self.table_header.setRowHidden(0, True)
        self.table_header.setFixedHeight(hdr_height)
        self.table_level.setFixedHeight(hdr_height)

        # Sync vertical header width for level and index (again, potentially updated)
        last_col = self.dataModel.header_shape[1] - 1
        if last_col < 0:
            idx_width = self.table_level.verticalHeader().width()
        else:
            idx_width = (self.table_level.columnViewportPosition(last_col) +
                         self.table_level.columnWidth(last_col) +
                         self.table_level.verticalHeader().width() + 5) # +5 for separator
        self.table_index.setFixedWidth(idx_width)
        self.table_level.setFixedWidth(idx_width)


if __name__ == '__main__':
    app = QApplication(sys.argv)

    # Example: Create viewer and load an Excel file
    viewer = ExcelViewer()
    # Replace 'your_file.xlsx' with the path to your Excel file
    file_path = r'D:\work\CanvasMind\output.xlsx'
    if viewer.setup_and_check(file_path):
        viewer.show()
        sys.exit(app.exec_())
    else:
        print("Failed to load the Excel file.")
        sys.exit(1)