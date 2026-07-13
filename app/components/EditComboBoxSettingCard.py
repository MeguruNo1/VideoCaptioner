from typing import List, Union

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QIcon
from qfluentwidgets import EditableComboBox, SettingCard
from qfluentwidgets.common.config import ConfigItem, qconfig


class EditComboBoxSettingCard(SettingCard):
    """可编辑的下拉框设置卡片"""

    currentTextChanged = pyqtSignal(str)

    def __init__(
        self,
        configItem: ConfigItem,
        icon: Union[str, QIcon],
        title: str,
        content: str = None,
        items: List[str] = None,
        parent=None,
    ):
        super().__init__(icon, title, content, parent)

        self.configItem = configItem
        self.items = items or []
        self._updating_from_user = False

        # 创建可编辑的组合框
        self.comboBox = EditableComboBox(self)
        for item in self.items:
            self.comboBox.addItem(item)

        # 设置布局
        self.hBoxLayout.addWidget(self.comboBox, 1, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

        # 设置最小宽度
        self.comboBox.setMinimumWidth(280)

        # 设置初始值
        self.setValue(qconfig.get(configItem))

        # 连接信号
        self.comboBox.currentTextChanged.connect(self.__onTextChanged)
        configItem.valueChanged.connect(self.setValue)

    def __onTextChanged(self, text: str):
        """当文本改变时触发"""
        self._updating_from_user = True
        try:
            qconfig.set(self.configItem, text)
            self.comboBox.setToolTip(text)
        finally:
            self._updating_from_user = False
        self.currentTextChanged.emit(text)

    def setValue(self, value: str):
        """设置值"""
        text = str(value or "")
        qconfig.set(self.configItem, text)
        self.comboBox.setToolTip(text)
        if self._updating_from_user:
            return
        if self.comboBox.text() == text:
            self.comboBox.setCursorPosition(0)
            return

        blocked = self.comboBox.blockSignals(True)
        self.comboBox.setText(text)
        self.comboBox.setCursorPosition(0)
        self.comboBox.blockSignals(blocked)

    def addItems(self, items: List[str]):
        """添加选项"""
        for item in items:
            self.comboBox.addItem(item)

    def setItems(self, items: List[str]):
        """重新设置选项列表"""
        self.comboBox.clear()
        self.items = items
        for item in items:
            self.comboBox.addItem(item)
