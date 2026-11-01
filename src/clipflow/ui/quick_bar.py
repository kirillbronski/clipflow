"""Quick settings in the download card, as in 4K: type, quality, folder and smart mode.

The chips keep no state of their own: each mirrors a field of the card's «Другие параметры»
(its items, its current text) and a choice sets that field, so both always agree.
"""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMenu, QPushButton, QSizePolicy, QWidget

from clipflow.domain.models import Service
from clipflow.ui.toggle import ToggleSwitch

SPACING = 8
STANDARD_HEIGHTS = (2160, 1440, 1080, 720, 480, 360)
# Short chip texts for Instagram's content choice; the menu keeps the full wording.
_SHORT_KINDS = {'all': 'chip.all_media', 'video': 'chip.video_only', 'photo': 'chip.photo_only'}
FOLDER_WIDTH = 180  # the folder chip's text is elided beyond this


class QuickBar(QWidget):
    def __init__(self, composer, translator, theme=None, parent=None):
        super().__init__(parent)
        self.composer = composer
        self.tr = translator
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING)
        # Never widens the card; a card too narrow for it moves it to a line of its own.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.kind_chip = self._chip(self._kind_items, self._kind_pick)
        self.quality_chip = self._chip(self._quality_items, self._quality_pick)
        self.folder_chip = self._chip(self._folder_items, self._folder_pick)
        for chip in (self.kind_chip, self.quality_chip, self.folder_chip):
            layout.addWidget(chip)
        layout.addSpacing(SPACING)
        self.smart_toggle = ToggleSwitch(theme=theme)
        # As in 4K, a bulb and a switch; the name lives in the tooltip and for screen readers.
        self.smart_label = QLabel('💡')
        self.tr.bind(self.smart_toggle, 'smart_mode_hint', setter='setToolTip')
        self.tr.bind(self.smart_label, 'smart_mode_hint', setter='setToolTip')
        self.tr.bind(self.smart_toggle, 'smart_mode', setter='setAccessibleName')
        layout.addWidget(self.smart_toggle)
        layout.addWidget(self.smart_label)
        layout.addStretch(1)
        self.tr.changed.connect(self.refresh)
        for box in (composer.format_box, composer.quality_box, composer.filter_box):
            box.currentIndexChanged.connect(self.refresh)
        composer.folder_input.textChanged.connect(self.refresh)
        composer.service_changed.connect(self.refresh)

    def _chip(self, items, pick):
        chip = QPushButton()
        chip.setObjectName('statusTab')
        chip.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        menu = QMenu(chip)
        menu.aboutToShow.connect(lambda: self._fill(menu, items(), pick))
        chip.setMenu(menu)
        return chip

    @staticmethod
    def _fill(menu, items, pick):
        menu.clear()
        for item in items:
            if item is None:
                menu.addSeparator()
                continue
            text, value, checked = item
            action = menu.addAction(text)
            action.setCheckable(checked is not None)
            action.setChecked(bool(checked))
            action.triggered.connect(lambda checked=False, v=value: pick(v))

    def _kind_box(self):
        composer = self.composer
        if composer.service == Service.INSTAGRAM:
            return composer.filter_box
        if composer.service == Service.YOUTUBE:
            return composer.format_box
        return None

    @staticmethod
    def _box_items(box):
        return [(box.itemText(i), i, i == box.currentIndex()) for i in range(box.count())]

    def _kind_items(self):
        box = self._kind_box()
        return self._box_items(box) if box is not None else []

    def _kind_pick(self, index):
        box = self._kind_box()
        if box is not None and box.isEnabled():
            box.setCurrentIndex(index)

    def _quality_items(self):
        """Probed heights when a link was checked, else the usual limits to choose from."""
        composer = self.composer
        current = composer.quality_box.currentData()
        heights = composer._heights or STANDARD_HEIGHTS
        items = [(self.tr.text('best_available'), None, current is None)]
        for height in heights:
            text = (
                f'{height}p' if composer._heights else self.tr.text('quality_limit', height=height)
            )
            items.append((text, height, current == height))
        return items

    def _quality_pick(self, height):
        self.composer.choose_quality(height)

    def _folder_items(self):
        box = self.composer.recent_box
        items = [
            (box.itemText(i), box.itemData(i), None) for i in range(box.count()) if box.itemData(i)
        ]
        return [*items, None, (self.tr.text('choose_folder_menu'), None, None)]

    def _folder_pick(self, folder):
        composer = self.composer
        if folder is None:
            composer._choose_folder()
            return
        composer.folder_input.setText(str(folder))
        composer._options_changed()

    def refresh(self):
        composer = self.composer
        box = self._kind_box()
        self.kind_chip.setVisible(box is not None)
        if box is not None:
            short = _SHORT_KINDS.get(box.currentData()) if box is composer.filter_box else None
            self.kind_chip.setText(self.tr.text(short) if short else box.currentText())
            self.kind_chip.setEnabled(box.isEnabled())
        quality = composer.quality_box
        self.quality_chip.setVisible(quality.isEnabled() and quality.count() > 0)
        # «Лучшее» is enough on the chip; the menu keeps the full wording.
        best = quality.currentData() is None
        self.quality_chip.setText(
            self.tr.text('quality_best_short') if best else quality.currentText()
        )
        folder = composer.folder_input.text().strip()
        self.folder_chip.setToolTip(folder)
        name = Path(folder).name if folder else ''
        label = '…/' + name if name else self.tr.text('folder')
        metrics = self.folder_chip.fontMetrics()
        self.folder_chip.setText(
            metrics.elidedText(label, Qt.TextElideMode.ElideLeft, FOLDER_WIDTH)
        )
        self.composer._arrange_quick_bar()
