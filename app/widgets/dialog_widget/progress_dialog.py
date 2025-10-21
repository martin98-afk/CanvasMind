"""
@author: mading
@license: (C) Copyright: LUCULENT Corporation Limited.
@contact: mading@luculent.net
@file: progress_dialog.py
@time: 2025/10/21 15:25
@desc: 
"""
from qfluentwidgets import MessageBoxBase, SubtitleLabel, IndeterminateProgressBar, BodyLabel, ProgressBar


class FluentLoadingDialog(MessageBoxBase):
    def __init__(self, title: str, max_value: int = 100, parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(title, self)
        self.infoLabel = BodyLabel("准备中...", self)
        self.progressBar = ProgressBar(self)
        self.progressBar.setRange(0, max_value)

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.infoLabel)
        self.viewLayout.addWidget(self.progressBar)

        self.yesButton.hide()
        self.cancelButton.hide()
        self.setFixedSize(320, 180)

    def set_progress(self, value: int):
        self.progressBar.setValue(value)

    def set_text(self, text: str):
        self.infoLabel.setText(text)