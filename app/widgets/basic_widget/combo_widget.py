from PyQt5.QtWidgets import QComboBox


class CustomComboBox(QComboBox):
    """自定义ComboBox，解决弹出窗口被遮挡问题"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
           QComboBox {
               background-color: transparent;
               border: 1px solid #545454;
               border-radius: 5px;
               padding: 5px 22px 5px 8px; /* 稍微增加上下padding */
               color: white;
               min-height: 18px;
               font-size: 14px;            /* 主框字体大小 */
               font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
           }
           QComboBox:hover {
               border: 1px solid #0078d4;
           }
           QComboBox::drop-down {
               subcontrol-origin: padding;
               subcontrol-position: top right;
               width: 20px;
               border: none;
           }
           QComboBox QAbstractItemView {
               background-color: #323232;
               border: 1px solid #545454;
               border-radius: 5px;
               selection-background-color: #0078d4;
               selection-color: white;
               color: white;
               outline: 0;
               padding: 4px 0;             /* 增加上下内边距，避免贴边 */
               font-size: 14px;            /* ⬅️ 关键：增大下拉项字体 */
               font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
           }
           QComboBox QAbstractItemView::item {
                min-height: 36px;      /* 从 32px → 36px */
                padding: 8px 16px;     /* 从 6px 12px → 8px 16px */
                border-bottom: 1px solid #444444; /* 添加分隔线更清晰 */
            }
           QComboBox QAbstractItemView::item:selected {
               background-color: #0078d4;
           }
       """)