from __future__ import annotations
import json
import re
import os
import subprocess
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(ROOT / 'vendor'))
from PySide6.QtCore import Qt, QThread, QTimer, QUrl, Signal, QPoint
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPen, QFont, QValidator, QIcon, QPixmap, QPolygon
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QListWidget, QFileDialog, QFrame, QSplitter, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QDoubleSpinBox, QProgressBar,
    QComboBox, QDialog, QFormLayout, QPlainTextEdit, QTabWidget, QDialogButtonBox, QMessageBox, QSlider, QStyle, QMenu, QWidgetAction, QScrollBar, QStyleOptionSpinBox, QStyleOptionComboBox, QLineEdit, QCheckBox, QScrollArea)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

VERSION = '2.0.3'
EXTENSIONS = {'.mp4', '.mkv', '.mov', '.avi', '.webm', '.m4v'}


class ProcessingThread(QThread):
    output = Signal(str)
    failure = Signal(str)
    def __init__(self, command, environment, parent):
        super().__init__(parent)
        self.command, self.environment = command, environment
        self.child, self.cancel_requested, self.exit_code = None, False, 1
    def run(self):
        try:
            self.child = subprocess.Popen(self.command, cwd=ROOT, env=self.environment,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                encoding='utf-8', errors='replace', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if self.cancel_requested:
                self.child.kill()
            for line in self.child.stdout:
                self.output.emit(line)
            self.exit_code = self.child.wait()
            self.child.stdout.close()
        except Exception as exc:
            self.failure.emit(str(exc))
    def kill(self):
        self.cancel_requested = True
        if self.child and self.child.poll() is None:
            self.child.kill()
    def waitForFinished(self, timeout):
        return self.wait(timeout)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
    temp.replace(path)


def clock(seconds):
    minutes, seconds = divmod(max(0, seconds), 60)
    hours, minutes = divmod(int(minutes), 60)
    return f'{hours:02}:{minutes:02}:{seconds:06.3f}'


def button(text, slot, primary=False):
    widget = QPushButton(text)
    if primary:
        widget.setProperty('primary', True)
    tips = {'Preview region': 'Play the selected region with one second of context on either side',
            'Apply': 'Save the edited start and end times for this region',
            'Remove': 'Delete the selected censor region',
            'Analyze video': 'Find censor words and phrases in the selected video',
            'Analyze queue': 'Analyze each queued video in order',
            'Settings': 'Choose processing hardware, models, words and phrases',
            'Export censored video': 'Save a censored copy using the current regions and censor style',
            'Cancel': 'Stop the current processing job',
            'View last export': 'Open the most recently exported video',
            '+  Add videos': 'Add videos to the review queue'}
    widget.setToolTip(tips.get(text, text))
    widget.clicked.connect(slot)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    return widget


class CitrusComboBox(QComboBox):
    def paintEvent(self, event):
        super().paintEvent(event)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        rect = self.style().subControlRect(QStyle.ComplexControl.CC_ComboBox, option, QStyle.SubControl.SC_ComboBoxArrow, self)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#ffc563' if self.isEnabled() else '#858971'))
        x, y = rect.center().x(), rect.center().y()
        painter.drawPolygon(QPolygon([QPoint(x-4,y-2),QPoint(x+4,y-2),QPoint(x,y+3)]))


class TriangleSpinBox(QDoubleSpinBox):
    def paintEvent(self, event):
        super().paintEvent(event)
        option = QStyleOptionSpinBox()
        self.initStyleOption(option)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#ffc563' if self.isEnabled() else '#858971'))
        for control, direction in ((QStyle.SubControl.SC_SpinBoxUp, -1), (QStyle.SubControl.SC_SpinBoxDown, 1)):
            rect = self.style().subControlRect(QStyle.ComplexControl.CC_SpinBox, option, control, self)
            x, y = rect.center().x(), rect.center().y()
            painter.drawPolygon(QPolygon([QPoint(x-4, y-direction*2), QPoint(x+4, y-direction*2), QPoint(x, y+direction*3)]))


class TimestampEdit(TriangleSpinBox):
    """Edit a duration without wrapping at midnight, retaining millisecond precision."""
    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setDecimals(3)
        self.setRange(0, 360000)
        self.setSingleStep(.05)
        self.setKeyboardTracking(False)
        self.setMinimumWidth(132)
        self.setToolTip('Hours:minutes:seconds.milliseconds (HH:MM:SS.mmm)')
    def textFromValue(self, value):
        millis = round(value * 1000)
        hours, millis = divmod(millis, 3600000)
        minutes, millis = divmod(millis, 60000)
        seconds, millis = divmod(millis, 1000)
        return f'{hours:02}:{minutes:02}:{seconds:02}.{millis:03}'
    def valueFromText(self, text):
        hours, minutes, seconds = text.split(':')
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    def validate(self, text, pos):
        if re.fullmatch(r'\d{1,3}:[0-5]\d:[0-5]\d\.\d{3}', text):
            state = QValidator.State.Acceptable if self.valueFromText(text) <= self.maximum() else QValidator.State.Invalid
        elif re.fullmatch(r'[\d:.]{0,13}', text):
            state = QValidator.State.Intermediate
        else:
            state = QValidator.State.Invalid
        return state, text, pos


class Timeline(QWidget):
    seek = Signal(float)
    view_changed = Signal()
    def __init__(self):
        super().__init__()
        self.duration, self.position, self.events = 0, 0, []
        self.draft_start = None
        self.zoom, self.offset = 1., 0.
        self.setMinimumHeight(62)
        self.setToolTip('Click to seek. Scroll to zoom around the pointer. Drag the bar below to pan.')
    @property
    def span(self):
        return self.duration / self.zoom if self.duration else 0
    def set_view(self, zoom, offset):
        self.zoom = max(1., min(zoom, max(1., self.duration)))
        self.offset = max(0., min(offset, self.duration - self.span))
        self.update()
        self.view_changed.emit()
    def zoom_by(self, factor, fraction=None):
        if not self.duration:
            return
        if fraction is None:
            fraction = max(0., min(1., (self.position-self.offset) / self.span))
        anchor = self.offset + fraction * self.span
        zoom = max(1., min(self.zoom * factor, max(1., self.duration)))
        self.set_view(zoom, anchor - fraction * self.duration / zoom)
    def pan(self, value):
        self.set_view(self.zoom, value / 10000 * (self.duration - self.span))
    def follow(self, position):
        self.position = position
        if self.span and not self.offset <= position <= self.offset + self.span:
            self.set_view(self.zoom, position - self.span / 2)
        self.update()
    def fraction_at(self, x):
        return max(0., min(1., (x-12) / max(1, self.width()-24)))
    def time_at(self, x):
        return self.offset + self.fraction_at(x) * self.span
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = max(1, self.width() - 24)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor('#3b412a'))
        p.drawRoundedRect(12, 12, width, 22, 6, 6)
        if self.span:
            def region(start, end, color):
                left, right = max(start, self.offset), min(end, self.offset + self.span)
                if right < left:
                    return
                p.setBrush(QColor(color))
                p.drawRoundedRect(int(12 + (left-self.offset)/self.span*width), 12,
                                  max(2, int((right-left)/self.span*width)), 22, 3, 3)
            p.save()
            p.setClipRect(12, 7, width, 33)
            for item in self.events:
                region(item['start'], item['end'], '#ff9f24')
            if self.draft_start is not None:
                region(*sorted((self.draft_start, self.position)), '#80be54')
            if self.offset <= self.position <= self.offset + self.span:
                p.setPen(QPen(QColor('#fff4dc'), 2))
                x = int(12 + (self.position-self.offset)/self.span*width)
                p.drawLine(x, 7, x, 39)
            p.restore()
        p.setPen(QColor('#b5b79a'))
        p.drawText(12, 56, clock(self.offset))
        p.drawText(self.width() - 108, 56, clock(self.offset + self.span))
        p.drawText(self.width()//2 - 48, 56, clock(self.position))
    def mousePressEvent(self, event):
        if self.duration and event.button() == Qt.MouseButton.LeftButton:
            self.seek.emit(self.time_at(event.position().x()))
    def wheelEvent(self, event):
        if self.duration and event.angleDelta().y():
            self.zoom_by(2 if event.angleDelta().y() > 0 else .5, self.fraction_at(event.position().x()))
            event.accept()



class Settings(QDialog):
    download_requested = Signal(str)
    def __init__(self, parent, config, devices):
        super().__init__(parent)
        self.setWindowTitle('JuicyCensor settings')
        self.setMinimumSize(660, 710)
        self.config = dict(config)
        layout = QVBoxLayout(self)
        title = QLabel('Make it yours')
        title.setObjectName('sectionTitle')
        layout.addWidget(title)
        tabs = QTabWidget()
        layout.addWidget(tabs)
        processing = QWidget()
        form = QFormLayout(processing)
        form.setVerticalSpacing(16)
        self.backend = CitrusComboBox()
        for label, value in [('Automatic', 'auto'), ('NVIDIA · CUDA', 'cuda'), ('AMD / other GPU · Vulkan', 'vulkan'), ('CPU', 'cpu')]:
            self.backend.addItem(label, value)
        self.backend.setCurrentIndex(max(0, self.backend.findData(config.get('backend', 'auto'))))
        form.addRow('Acceleration', self.backend)
        self.gpu = CitrusComboBox()
        self.gpu.addItem('Automatic', 'auto')
        for device in devices:
            self.gpu.addItem(device['name'], device['id'])
        self.gpu.setCurrentIndex(max(0, self.gpu.findData(config.get('vulkan_device', 'auto'))))
        form.addRow('Graphics card', self.gpu)
        self.model = CitrusComboBox()
        self.model.addItems(['large-v3', 'medium.en', 'small.en', 'base.en'])
        self.model.setCurrentText(config.get('model', 'large-v3'))
        form.addRow('NVIDIA / CPU model', self.model)
        self.vmodel = CitrusComboBox()
        self.vmodel.addItems(['base.en', 'small.en', 'medium.en', 'large-v3'])
        self.vmodel.setCurrentText(config.get('vulkan_model', 'base.en'))
        form.addRow('Vulkan model', self.vmodel)
        form.addRow('', button('Download Vulkan model', self.download))
        note = QLabel('The base.en model is fast and compact. Larger models require more memory and storage.\nVulkan uses your GPU for transcription and your CPU to align words with the audio.')
        note.setWordWrap(True)
        note.setObjectName('muted')
        form.addRow(note)
        self.language = CitrusComboBox()
        for label, value in [('English', 'en'), ('Detect language', 'auto'), ('Spanish', 'es'), ('French', 'fr'), ('German', 'de')]:
            self.language.addItem(label, value)
        self.language.setCurrentIndex(max(0, self.language.findData(config.get('language', 'en'))))
        form.addRow('Language', self.language)
        self.pre, self.post = TriangleSpinBox(), TriangleSpinBox()
        for widget, key in [(self.pre, 'pre_padding'), (self.post, 'post_padding')]:
            widget.setRange(0, 2)
            widget.setSingleStep(.02)
            widget.setSuffix(' s')
            widget.setValue(config.get(key, .1))
        form.addRow('Padding before each word', self.pre)
        form.addRow('Padding after each word', self.post)
        self.backend.setToolTip('Choose how speech analysis runs. Select the video encoder separately on the Export tab.')
        self.gpu.setToolTip('Choose the graphics card used for Vulkan speech analysis. This setting does not change the export encoder.')
        self.model.setToolTip('Speech model for NVIDIA CUDA or CPU analysis. Larger models use more memory and take longer.')
        self.vmodel.setToolTip('Speech model for Vulkan analysis. Download the selected model before using it.')
        self.language.setToolTip('Language of the spoken audio. Models ending in .en support English only.')
        self.pre.setToolTip('Extra time to censor before each detected word, in seconds. Reanalyze after changing this.')
        self.post.setToolTip('Extra time to censor after each detected word, in seconds. Reanalyze after changing this.')
        tabs.addTab(processing, 'Processing')
        export = QWidget()
        export_form = QFormLayout(export)
        export_form.setVerticalSpacing(12)
        path_row = QHBoxLayout()
        self.export_path = QLineEdit(str(config.get('export_path') or ROOT / 'outputs' / 'censored'))
        self.export_path.setToolTip('Choose where exported videos are saved. The folder is created when needed. Reports are saved in outputs/reports inside the app folder.')
        path_row.addWidget(self.export_path, 1)
        browse = button('Browse…', self.browse_export_path)
        browse.setToolTip('Choose where to save exported videos')
        path_row.addWidget(browse)
        export_form.addRow('Export path', path_row)
        self.no_spaces = QCheckBox('Use filenames without spaces')
        self.no_spaces.setChecked(bool(config.get('export_no_spaces', False)))
        self.no_spaces.setToolTip('Replace spaces in exported filenames with underscores. A unique suffix prevents existing files from being overwritten.')
        export_form.addRow('', self.no_spaces)
        self.export_controls = {}
        choices = [
            ('export_quality', 'Export preset', 'original', [
                ('Keep original video quality · fastest', 'original'),
                ('High quality · larger file', 'high'), ('Balanced', 'balanced'),
                ('Smaller file', 'small'), ('Custom', 'custom')]),
            ('export_encoder', 'Video encoder', 'copy' if config.get('export_quality', 'original') == 'original' else 'auto', [
                ('Automatic · prefer hardware', 'auto'), ('Hardware (NVIDIA, H.264)', 'h264_nvenc'), ('Hardware (NVIDIA, HEVC)', 'hevc_nvenc'), ('Hardware (NVIDIA, AV1)', 'av1_nvenc'),
                ('Hardware (AMD, H.264)', 'h264_amf'), ('Hardware (AMD, HEVC)', 'hevc_amf'),
                ('Hardware (Intel, H.264)', 'h264_qsv'), ('Hardware (Intel, HEVC)', 'hevc_qsv'),
                ('Software (x264, H.264)', 'libx264'), ('Software (x265, HEVC)', 'libx265'), ('Copy original video', 'copy')]),
            ('export_format', 'Export format', 'mp4', [('MP4 (.mp4)', 'mp4'), ('Matroska (.mkv)', 'mkv')]),
            ('export_audio_encoder', 'Audio encoder', 'aac', [('AAC · widely compatible', 'aac'), ('Opus · Matroska only', 'libopus')]),
            ('export_video_quality', 'Video quality', {'high': '18', 'small': '28'}.get(config.get('export_quality'), '23'), [
                ('Original', 'original'), ('High', '18'), ('Balanced', '23'), ('Smaller file', '28')]),
            ('export_resolution', 'Maximum resolution', 'original', [
                ('Original', 'original'), ('3840 × 2160 · 4K', '2160p'),
                ('2560 × 1440 · 1440p', '1440p'), ('1920 × 1080 · 1080p', '1080p'),
                ('1280 × 720', '720p'), ('854 × 480', '480p')]),
            ('export_fps', 'Frame rate', 'original', [
                ('Original', 'original'), ('24 fps', '24'), ('30 fps', '30'), ('60 fps', '60')]),
            ('export_preset', 'Encoding speed', 'fast', [
                ('Fast', 'fast'), ('Balanced', 'medium'), ('Slower · smaller file', 'slow')]),
            ('export_audio_bitrate', 'Audio quality', '192', [
                ('Original', 'original'),
                ('128 kbps · smaller file', '128'), ('192 kbps · balanced', '192'),
                ('256 kbps · high', '256'), ('320 kbps · highest', '320')])]
        for key, label, default, options in choices:
            combo = CitrusComboBox()
            for text, value in options:
                combo.addItem(text, value)
            combo.setCurrentIndex(max(0, combo.findData(str(config.get(key, default)))))
            self.export_controls[key] = combo
            export_form.addRow(label, combo)
        self.export_controls['export_quality'].currentIndexChanged.connect(self.update_export_controls)
        tips = {
            'export_quality': 'Apply a preset. Editing any individual export option switches to Custom.',
            'export_encoder': 'Automatic selects working H.264 hardware, then CPU. HEVC and AV1 can save space but need compatible players. Manual selections are tested before export. Copy preserves the original video stream.',
            'export_format': 'MP4 is widely compatible. Matroska supports Opus audio. Selecting MP4 switches Opus to AAC.',
            'export_audio_encoder': 'AAC works with MP4 and Matroska. Choosing Opus switches the format to Matroska.',
            'export_video_quality': 'Original preserves the existing video stream. High, Balanced, and Smaller file re-encode the video. Results vary by encoder.',
            'export_resolution': 'Limit the output dimensions without upscaling or stretching. Changing this setting enables video re-encoding.',
            'export_fps': 'Original keeps the source frame rate. Other choices may drop or duplicate frames and require video re-encoding.',
            'export_preset': 'Slower encoding can produce smaller files at similar quality. Results depend on the encoder. Changing this setting enables video re-encoding.',
            'export_audio_bitrate': 'Original matches the source audio bitrate when reported (8–512 kbps); otherwise uses 192 kbps. Censoring still re-encodes audio, so Original is not lossless. Higher fixed bitrates use more space.'}
        for key, combo in self.export_controls.items():
            combo.setToolTip(tips[key])
            if key != 'export_quality':
                combo.currentIndexChanged.connect(lambda _, key=key: self.custom_export(key))
        export_note = QLabel('Choose where and how to save your censored copy. Original files remain unchanged.\n\nAutomatic selects an available H.264 hardware encoder and falls back to the CPU. You can also select HEVC or AV1 where supported.\n\nChanging an option selects the Custom preset. Export settings apply without analyzing the video again.')
        export_note.setWordWrap(True)
        export_note.setObjectName('muted')
        export_form.addRow(export_note)
        export_scroll = QScrollArea()
        export_scroll.setWidgetResizable(True)
        export_scroll.setWidget(export)
        tabs.addTab(export_scroll, 'Export')
        if self.export_controls['export_encoder'].currentData() == 'copy':
            self.set_export_value('export_video_quality', 'original')
        if self.export_controls['export_quality'].currentData() == 'original':
            self.set_export_value('export_audio_bitrate', 'original')
        self.word_lists = {}
        for filename, label in [('banned_words.txt', 'Words'), ('banned_phrases.txt', 'Phrases')]:
            editor = QPlainTextEdit((ROOT / filename).read_text(encoding='utf-8'))
            editor.setPlaceholderText('One entry per line')
            self.word_lists[filename] = editor
            tabs.addTab(editor, label)
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        controls.accepted.connect(self.save)
        controls.rejected.connect(self.reject)
        layout.addWidget(controls)
    def browse_export_path(self):
        path = QFileDialog.getExistingDirectory(self, 'Choose export folder', self.export_path.text())
        if path:
            self.export_path.setText(path)
    def set_export_value(self, key, value):
        combo = self.export_controls[key]
        combo.blockSignals(True)
        combo.setCurrentIndex(combo.findData(value))
        combo.blockSignals(False)
    def update_export_controls(self):
        preset = self.export_controls['export_quality'].currentData()
        if preset == 'custom':
            return
        values = {'export_encoder': 'copy' if preset == 'original' else 'auto',
                  'export_video_quality': {'original':'original', 'high':'18', 'small':'28'}.get(preset, '23'),
                  'export_resolution':'original', 'export_fps':'original',
                  'export_preset':'fast', 'export_audio_bitrate':'original' if preset == 'original' else '192'}
        for key, value in values.items():
            self.set_export_value(key, value)
    def custom_export(self, key):
        self.set_export_value('export_quality', 'custom')
        if key == 'export_audio_encoder' and self.export_controls[key].currentData() == 'libopus':
            self.set_export_value('export_format', 'mkv')
        elif key == 'export_format' and self.export_controls[key].currentData() == 'mp4':
            self.set_export_value('export_audio_encoder', 'aac')
        encoder = self.export_controls['export_encoder'].currentData()
        if key == 'export_video_quality' and self.export_controls[key].currentData() == 'original':
            self.set_export_value('export_encoder', 'copy')
            encoder = 'copy'
            key = 'export_encoder'
        if key == 'export_encoder' and encoder == 'copy':
            self.set_export_value('export_video_quality', 'original')
            for name in ('export_resolution', 'export_fps'):
                self.set_export_value(name, 'original')
        elif key in ('export_resolution', 'export_fps', 'export_video_quality', 'export_preset') and encoder == 'copy':
            self.set_export_value('export_encoder', 'auto')
        if self.export_controls['export_encoder'].currentData() != 'copy' and self.export_controls['export_video_quality'].currentData() == 'original':
            self.set_export_value('export_video_quality', '23')
    def download(self):
        self.download_requested.emit(self.vmodel.currentText())
        self.reject()
    def save(self):
        path = Path(self.export_path.text().strip()).expanduser()
        if not self.export_path.text().strip() or not path.is_absolute():
            QMessageBox.warning(self, 'Choose an export folder', 'Enter a full folder path or use Browse.')
            return
        self.config.update(export_path=str(path), export_no_spaces=self.no_spaces.isChecked())
        self.config.update({key: combo.currentData() for key, combo in self.export_controls.items()})
        self.config.update(backend=self.backend.currentData(), vulkan_device=self.gpu.currentData(),
                           model=self.model.currentText(), vulkan_model=self.vmodel.currentText(),
                           language=self.language.currentData(), pre_padding=self.pre.value(), post_padding=self.post.value())
        try:
            write_json(ROOT / 'config.json', self.config)
            for name, editor in self.word_lists.items():
                (ROOT / name).write_text(editor.toPlainText().strip() + '\n', encoding='utf-8')
        except OSError as exc:
            QMessageBox.warning(self, 'Could not save', str(exc))
            return
        self.accept()


STYLE = '''
QWidget { background: #191710; color: #fff4dc; font-family: "Segoe UI"; font-size: 13px; }
QMainWindow { background: #191710; }
QFrame#sidebar { background: #12150f; border-right: 1px solid #383e28; }
QFrame#card { background: #242219; border: 1px solid #44402c; border-radius: 12px; }
QWidget#markPanel { background: #242219; }
QLabel { background: transparent; }
QLabel#logo { color: #ffac35; font-size: 25px; font-weight: 800; letter-spacing: 2px; }
QLabel#heading { font-size: 27px; font-weight: 700; }
QLabel#sectionTitle { font-size: 19px; font-weight: 600; }
QLabel#muted { color: #b5b79a; }
QLabel#badge { color: #ffbf63; background: #342b1a; border: 1px solid #64502d; border-radius: 16px; padding: 6px 14px; font-size: 12px; font-weight: 600; }
QScrollBar:horizontal { background: #24291b; height: 12px; border: 1px solid #51563a; border-radius: 5px; }
QScrollBar::handle:horizontal { background: #7a874e; min-width: 24px; border-radius: 4px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
QSlider::groove:horizontal { height: 6px; background: #414a2c; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #ff9f24; border-radius: 3px; }
QSlider::handle:horizontal { background: #ffc563; border: 1px solid #ff9f24; width: 14px; margin: -5px 0; border-radius: 7px; }
QPushButton { background: #353a27; border: 1px solid #51563a; border-radius: 7px; padding: 9px 14px; font-weight: 600; }
QPushButton:focus { border: 1px solid #ffb94f; }
QToolTip { background: #2d3021; color: #fff4dc; border: 1px solid #64502d; padding: 6px; }
QScrollArea { border: 0; background: #191710; }
QScrollBar:vertical { background: #24291b; width: 12px; border: 0; }
QScrollBar::handle:vertical { background: #7a874e; min-height: 26px; border-radius: 5px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #7a874e; border-radius: 3px; background: #24291b; }
QCheckBox::indicator:checked { background: #ff9f24; border-color: #ffc563; }
QPushButton:hover { background: #465031; }
QPushButton:pressed { background: #536039; }
QPushButton[primary="true"] { background: #ff9f24; color: #261b0a; border: 0; }
QPushButton[primary="true"]:hover { background: #ffb94f; }
QPushButton:disabled { background: #25291d; color: #858971; border-color: #3c422c; }
QListWidget { background: #12150f; border: 0; outline: none; }
QListWidget::item { padding: 13px 8px; border-radius: 7px; }
QListWidget::item:selected { background: #42462d; color: #fff; }
QTableWidget { background: #242219; alternate-background-color: #2d3021; gridline-color: #41432d; border: 0; selection-background-color: #525735; }
QHeaderView::section { background: #353824; color: #d1cfaf; padding: 9px; border: 0; font-weight: 600; }
QComboBox, QDoubleSpinBox, QPlainTextEdit, QLineEdit { background: #2d3021; border: 1px solid #51563a; border-radius: 6px; padding: 7px; }
QDoubleSpinBox { padding-right: 23px; }
QDoubleSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 19px; background: #353a27; border-top-right-radius: 5px; }
QDoubleSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 19px; background: #353a27; border-bottom-right-radius: 5px; }
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover { background: #465031; }
QDoubleSpinBox::up-arrow, QDoubleSpinBox::down-arrow { width: 0; height: 0; }
QComboBox { padding: 8px 32px 8px 10px; min-height: 20px; }
QComboBox::drop-down { subcontrol-origin: border; subcontrol-position: top right; width: 28px; border: 0; background: transparent; }
QComboBox::down-arrow { width: 0; height: 0; }
QComboBox QAbstractItemView { background: #353824; selection-background-color: #626b40; }
QProgressBar { border: 1px solid #537044; border-radius: 8px; background: #20321c; color: white; text-align: center; font-weight: 700; }
QProgressBar::chunk { background: #398b38; border-radius: 7px; }
QTabBar::tab { padding: 12px 20px; background: #282d1e; }
QTabBar::tab:selected { background: #434c2b; color: #ffb94f; }
QTabWidget::pane { border: 1px solid #414a2c; }
QSplitter::handle { background: #191710; width: 10px; }
'''


class OrangeMark(QWidget):
    """A small painted orange with a leaf; no external image assets needed."""
    def __init__(self):
        super().__init__()
        self.setFixedSize(70, 66)
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor('#ff9f24'))
        p.drawEllipse(8, 17, 48, 46)
        p.setBrush(QColor('#ffc563'))
        p.drawEllipse(15, 23, 14, 9)
        p.setBrush(QColor('#79b84b'))
        p.translate(35, 16)
        p.rotate(-28)
        p.drawEllipse(0, -7, 26, 12)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f'JuicyCensor · {VERSION}')
        self.resize(1390, 920)
        self.setMinimumSize(1080, 760)
        self.setAcceptDrops(True)
        self.config = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
        self.devices, self.reviews, self.queue_paths = [], {}, []
        self.state, self.state_path = None, None
        self.process, self.job, self.cancelled, self.received_result = None, {}, False, False
        self.pending, self.buffer, self.preview_end = [], '', None
        self.mark_start = None
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(.65)
        self.player.setAudioOutput(self.audio)
        self.build_ui()
        self.player.playbackStateChanged.connect(self.sync_play_icon)
        self.player.positionChanged.connect(self.position_changed)
        self.player.durationChanged.connect(self.duration_changed)
        self.player.errorOccurred.connect(lambda error, text: self.set_status('Preview unavailable: ' + text))
        self.start_job({'action': 'probe'})

    def build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        side = QFrame()
        side.setObjectName('sidebar')
        side.setFixedWidth(258)
        layout = QVBoxLayout(side)
        layout.setContentsMargins(20, 26, 20, 22)
        logo = QLabel('JUICYCENSOR')
        logo.setObjectName('logo')
        layout.addWidget(OrangeMark())
        layout.addWidget(logo)
        tag = QLabel(f'{VERSION}  /  LOCAL PROCESSING')
        tag.setObjectName('muted')
        tag.setStyleSheet('font-size: 10px; letter-spacing: 1px')
        layout.addWidget(tag)
        layout.addSpacing(30)
        layout.addWidget(button('+  Add videos', self.add_dialog, True))
        label = QLabel('YOUR QUEUE')
        label.setObjectName('muted')
        layout.addSpacing(14)
        layout.addWidget(label)
        self.queue = QListWidget()
        self.queue.currentRowChanged.connect(self.select_video)
        layout.addWidget(self.queue, 1)
        self.queue_btn = button('Analyze queue', self.analyze_queue)
        layout.addWidget(self.queue_btn)
        self.settings_btn = button('Settings', self.open_settings)
        layout.addWidget(self.settings_btn)
        runtime_button = button('Runtime setup', self.setup_runtime)
        runtime_button.setToolTip('Install, repair, or switch between the CPU/AMD and NVIDIA processing environments')
        layout.addWidget(runtime_button)
        self.runtime_button = runtime_button
        layout.addWidget(button('Open output folder', self.open_outputs))
        outer.addWidget(side)
        area = QVBoxLayout()
        area.setContentsMargins(26, 24, 26, 20)
        area.setSpacing(16)
        outer.addLayout(area, 1)
        header = QHBoxLayout()
        heading = QVBoxLayout()
        title = QLabel('Review the Juice')
        title.setObjectName('heading')
        heading.addWidget(title)
        subtitle = QLabel('Detect. Review. Filter the Juice.')
        subtitle.setObjectName('muted')
        heading.addWidget(subtitle)
        header.addLayout(heading, 1)
        self.hardware = QLabel('Getting ready…')
        self.hardware.setObjectName('badge')
        self.hardware.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hardware.setFixedHeight(34)
        header.addWidget(self.hardware, 0, Qt.AlignmentFlag.AlignVCenter)
        area.addLayout(header)
        filebar = QHBoxLayout()
        self.filename = QLabel('Drop a video here to get started')
        self.filename.setObjectName('sectionTitle')
        filebar.addWidget(self.filename, 1)
        self.analyze_btn = button('Analyze video', self.analyze_selected, True)
        filebar.addWidget(self.analyze_btn)
        area.addLayout(filebar)
        split = QSplitter(Qt.Orientation.Horizontal)
        preview = QFrame()
        preview.setObjectName('card')
        preview_layout = QVBoxLayout(preview)
        self.video = QVideoWidget()
        self.video.setMinimumSize(360, 235)
        self.player.setVideoOutput(self.video)
        preview_layout.addWidget(self.video, 1)
        playback = QHBoxLayout()
        self.back_button = self.icon_button(QStyle.StandardPixmap.SP_MediaSeekBackward, 'Skip backward', lambda: self.skip_video(-1))
        self.play_button = self.icon_button(QStyle.StandardPixmap.SP_MediaPlay, 'Play video', self.toggle_play)
        self.forward_button = self.icon_button(QStyle.StandardPixmap.SP_MediaSeekForward, 'Skip forward', lambda: self.skip_video(1))
        for control in (self.back_button, self.play_button, self.forward_button):
            playback.addWidget(control)
        self.skip_amount = TriangleSpinBox()
        self.skip_amount.setRange(.1, 600)
        self.skip_amount.setDecimals(1)
        self.skip_amount.setValue(5)
        self.skip_amount.setSuffix(' s')
        self.skip_amount.setMaximumWidth(94)
        self.skip_amount.setToolTip('Seconds to skip with the backward and forward buttons')
        self.skip_amount.setAccessibleName('Playback skip duration')
        playback.addWidget(self.skip_amount)
        self.volume_button = self.icon_button(QStyle.StandardPixmap.SP_MediaVolume, 'Preview volume', self.show_volume)
        playback.addWidget(self.volume_button)
        self.volume_popup = QMenu(self)
        volume_panel = QWidget()
        volume_row = QHBoxLayout(volume_panel)
        self.mute_button = button('Mute', self.toggle_mute)
        self.mute_button.setToolTip('Mute or unmute preview audio')
        volume_row.addWidget(self.mute_button)
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(65)
        self.volume_slider.setMinimumWidth(150)
        self.volume_slider.setAccessibleName('Preview volume')
        self.volume_slider.setToolTip('Preview volume only; exported audio is unchanged')
        self.volume_slider.valueChanged.connect(self.change_volume)
        volume_row.addWidget(self.volume_slider)
        self.volume_label = QLabel('65%')
        self.volume_label.setMinimumWidth(36)
        volume_row.addWidget(self.volume_label)
        volume_action = QWidgetAction(self.volume_popup)
        volume_action.setDefaultWidget(volume_panel)
        self.volume_popup.addAction(volume_action)
        self.speed_button = button('×1', self.show_speed)
        self.speed_button.setToolTip('Change preview playback speed')
        self.speed_button.setAccessibleName('Playback speed')
        self.speed_button.setFixedWidth(62)
        playback.addWidget(self.speed_button)
        self.speed_popup = QMenu(self)
        speed_panel = QWidget()
        speed_layout = QVBoxLayout(speed_panel)
        self.speed_label = QLabel('Playback speed · ×1')
        speed_layout.addWidget(self.speed_label)
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(1, 16)
        self.speed_slider.setValue(4)
        self.speed_slider.setMinimumWidth(210)
        self.speed_slider.setAccessibleName('Playback speed slider')
        self.speed_slider.setToolTip('Preview speed from ×0.25 to ×4; exported video speed is unchanged')
        self.speed_slider.valueChanged.connect(self.change_speed)
        speed_layout.addWidget(self.speed_slider)
        normal_speed = button('Normal speed', lambda: self.speed_slider.setValue(4))
        normal_speed.setToolTip('Reset preview playback to ×1')
        speed_layout.addWidget(normal_speed)
        speed_action = QWidgetAction(self.speed_popup)
        speed_action.setDefaultWidget(speed_panel)
        self.speed_popup.addAction(speed_action)
        playback.addStretch()
        playback.addWidget(button('Preview region', self.preview_region))
        preview_layout.addLayout(playback)
        self.scissors = button('', self.begin_mark)
        pix = QPixmap(24, 24)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor('#ffc563'), 2))
        painter.drawEllipse(2, 3, 6, 6)
        painter.drawEllipse(2, 15, 6, 6)
        painter.drawLine(7, 8, 21, 19)
        painter.drawLine(7, 16, 21, 5)
        painter.end()
        self.scissors.setIcon(QIcon(pix))
        self.scissors.setToolTip('Start censor at current playback')
        self.scissors.setAccessibleName('Start censor at current playback')
        self.scissors.setFixedWidth(40)
        playback.insertWidget(5, self.scissors)
        self.mark_panel = QWidget()
        self.mark_panel.setObjectName('markPanel')
        mark_layout = QHBoxLayout(self.mark_panel)
        mark_layout.setContentsMargins(0, 0, 0, 0)
        reset = button('Set censor', self.begin_mark)
        reset.setToolTip('Move the selection start to the current playback position')
        finish = button('End censor', self.finish_mark, True)
        finish.setToolTip('End the selection at the current playback position and save the censor region')
        cancel_mark = button('Cancel', self.cancel_mark)
        cancel_mark.setToolTip('Discard this selection without adding a censor region')
        for control in (reset, finish, cancel_mark):
            mark_layout.addWidget(control)
        preview_layout.addWidget(self.mark_panel)
        self.mark_panel.hide()
        self.timeline = Timeline()
        self.timeline.seek.connect(lambda value: self.player.setPosition(round(value * 1000)))
        preview_layout.addWidget(self.timeline)
        zoom_row = QHBoxLayout()
        self.zoom_out = button('', lambda: self.timeline.zoom_by(.5))
        self.zoom_out.setIcon(self.zoom_icon(False))
        self.zoom_out.setToolTip('Zoom out of the timeline')
        self.zoom_out.setAccessibleName('Zoom out')
        self.zoom_in = button('', lambda: self.timeline.zoom_by(2))
        self.zoom_in.setIcon(self.zoom_icon(True))
        self.zoom_in.setToolTip('Zoom in around the playback position for precise seeking')
        self.zoom_in.setAccessibleName('Zoom in')
        for control in (self.zoom_out, self.zoom_in):
            control.setFixedWidth(38)
            zoom_row.addWidget(control)
        self.zoom_label = QLabel('1×')
        zoom_row.addWidget(self.zoom_label)
        self.timeline_pan = QScrollBar(Qt.Orientation.Horizontal)
        self.timeline_pan.setRange(0, 10000)
        self.timeline_pan.setToolTip('Move the visible timeline window without changing playback')
        self.timeline_pan.setAccessibleName('Pan timeline')
        self.timeline_pan.valueChanged.connect(self.timeline.pan)
        zoom_row.addWidget(self.timeline_pan, 1)
        fit = button('Fit', lambda: self.timeline.set_view(1, 0))
        fit.setToolTip('Show the entire video timeline')
        zoom_row.addWidget(fit)
        preview_layout.addLayout(zoom_row)
        self.timeline.view_changed.connect(self.sync_timeline_zoom)
        self.sync_timeline_zoom()
        split.addWidget(preview)
        editor = QFrame()
        editor.setObjectName('card')
        edits = QVBoxLayout(editor)
        edits.setContentsMargins(18, 18, 18, 18)
        self.region_count = QLabel('Censor regions')
        self.region_count.setObjectName('sectionTitle')
        edits.addWidget(self.region_count)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(['Start', 'End', 'Match'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.itemSelectionChanged.connect(self.select_region)
        edits.addWidget(self.table, 1)
        fields = QHBoxLayout()
        self.start, self.end = TimestampEdit(), TimestampEdit()
        for label, spin in [('Start', self.start), ('End', self.end)]:
            caption = QLabel(label)
            caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
            fields.addWidget(caption)
            spin.setDecimals(3)
            spin.setRange(0, 360000)
            spin.setSingleStep(.05)
            fields.addWidget(spin)
        edits.addLayout(fields)
        region_buttons = QHBoxLayout()
        region_buttons.addWidget(button('Apply', self.apply_region))
        region_buttons.addWidget(button('Remove', self.remove_region))
        edits.addLayout(region_buttons)
        info = QLabel('Use the scissors to mark a start, then end the censor selection.\nFine-tune Start and End here. Changes save automatically.')
        info.setObjectName('muted')
        info.setWordWrap(True)
        edits.addWidget(info)
        split.addWidget(editor)
        split.setSizes([580, 480])
        area.addWidget(split, 1)
        footer = QHBoxLayout()
        footer.addWidget(QLabel('Censor style'))
        self.mode = CitrusComboBox()
        self.mode.setMinimumWidth(215)
        self.mode.setToolTip("Choose the sound used inside censor regions when exporting")
        for label, value in [('Continuous beep', 'continuous_beep'), ('Pulse beep', 'pulse_beep'), ('Custom beep', 'custom_beep'), ('Mute', 'mute')]:
            self.mode.addItem(label, value)
        self.mode.setCurrentIndex(max(0, self.mode.findData(self.config.get('censor_mode'))))
        footer.addWidget(self.mode)
        footer.addStretch()
        self.open_result_btn = button('View last export', self.open_result)
        self.open_result_btn.setEnabled(False)
        footer.addWidget(self.open_result_btn)
        self.render_btn = button('Export censored video', self.render, True)
        footer.addWidget(self.render_btn)
        area.addLayout(footer)
        statusbar = QHBoxLayout()
        self.status = QLabel('Ready. Add a video or drop files into the window.')
        self.status.setWordWrap(True)
        self.status.setObjectName('muted')
        statusbar.addWidget(self.status, 1)
        self.cancel_btn = button('Cancel', self.cancel)
        statusbar.addWidget(self.cancel_btn)
        area.addLayout(statusbar)
        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        self.progress.setFormat("%p%")
        self.progress.setFixedHeight(26)
        self.progress.setValue(0)
        area.addWidget(self.progress)
        self.update_controls()

    def set_status(self, message):
        self.status.setText(message)
    def toggle_mute(self):
        self.audio.setMuted(not self.audio.isMuted())
        self.sync_volume_icon()
        self.volume_label.setText('0%' if self.audio.isMuted() else f'{self.volume_slider.value()}%')
    def change_volume(self, value):
        self.audio.setVolume(value / 100)
        self.audio.setMuted(value == 0)
        self.sync_volume_icon()
        self.volume_label.setText(f'{value}%')
    def zoom_icon(self, plus):
        pix = QPixmap(24, 24)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor('#ffc563'), 2))
        painter.drawEllipse(3, 3, 13, 13)
        painter.drawLine(15, 15, 21, 21)
        painter.drawLine(6, 9, 13, 9)
        if plus:
            painter.drawLine(9, 6, 9, 13)
        painter.end()
        return QIcon(pix)
    def show_speed(self):
        self.speed_popup.popup(self.speed_button.mapToGlobal(self.speed_button.rect().bottomLeft()))
    def change_speed(self, value):
        rate = value / 4
        self.player.setPlaybackRate(rate)
        self.speed_button.setText(f'×{rate:g}')
        self.speed_label.setText(f'Playback speed · ×{rate:g}')
    def media_icon(self, icon):
        pix = self.style().standardIcon(icon).pixmap(20, 20)
        painter = QPainter(pix)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(pix.rect(), QColor('#ffc563'))
        painter.end()
        return QIcon(pix)
    def icon_button(self, icon, tooltip, slot):
        control = button('', slot)
        control.setIcon(self.media_icon(icon))
        control.setFixedWidth(40)
        control.setToolTip(tooltip)
        control.setAccessibleName(tooltip)
        return control
    def sync_play_icon(self, *_):
        playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self.play_button.setIcon(self.media_icon(QStyle.StandardPixmap.SP_MediaPause if playing else QStyle.StandardPixmap.SP_MediaPlay))
        self.play_button.setToolTip('Pause video' if playing else 'Play video')
        self.play_button.setAccessibleName(self.play_button.toolTip())
    def sync_volume_icon(self):
        muted = self.audio.isMuted() or self.audio.volume() == 0
        self.volume_button.setIcon(self.media_icon(QStyle.StandardPixmap.SP_MediaVolumeMuted if muted else QStyle.StandardPixmap.SP_MediaVolume))
        self.mute_button.setText('Unmute' if self.audio.isMuted() else 'Mute')
    def show_volume(self):
        self.volume_popup.popup(self.volume_button.mapToGlobal(self.volume_button.rect().bottomLeft()))
    def skip_video(self, direction):
        self.preview_end = None
        target = self.player.position() + round(direction * self.skip_amount.value() * 1000)
        self.player.setPosition(max(0, min(self.player.duration(), target)))
    def begin_mark(self):
        if self.process or not self.state:
            self.set_status('Analyze this video before marking censor regions.')
            return
        self.preview_end = None
        self.mark_start = min(self.player.position() / 1000, self.state['duration'])
        self.timeline.draft_start = self.mark_start
        self.timeline.update()
        self.scissors.setEnabled(False)
        self.mark_panel.show()
        self.set_status(f'Start: {clock(self.mark_start)}. Play or seek to the end, then choose End censor.')
    def cancel_mark(self):
        self.mark_start = None
        self.timeline.draft_start = None
        self.timeline.update()
        self.mark_panel.hide()
        self.scissors.setEnabled(self.process is None and self.state is not None)
    def finish_mark(self):
        if self.mark_start is None or self.process or not self.state:
            return
        end = min(self.player.position() / 1000, self.state['duration'])
        if end <= self.mark_start:
            self.set_status('Move playback after the selection start, or use Set censor to change it.')
            return
        self.player.pause()
        self.state['events'].append({'start': self.mark_start, 'end': end, 'matched': 'Manual region', 'kind': 'manual', 'source': 'manual'})
        self.cancel_mark()
        self.save_review()
        self.table.selectRow(len(self.state['events']) - 1)
        self.set_status('Censor region added. Fine-tune its Start and End if needed.')
    def selected_path(self):
        row = self.queue.currentRow()
        return self.queue_paths[row] if 0 <= row < len(self.queue_paths) else None
    def update_controls(self):
        busy = self.process is not None
        self.analyze_btn.setEnabled(not busy and self.selected_path() is not None)
        self.queue_btn.setEnabled(not busy and bool(self.queue_paths))
        self.settings_btn.setEnabled(not busy)
        self.runtime_button.setEnabled(not busy)
        self.queue.setEnabled(not busy)
        self.render_btn.setEnabled(not busy and bool(self.state and self.state['events']))
        self.table.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy)
        self.scissors.setEnabled(not busy and self.state is not None and self.mark_start is None)
        self.mark_panel.setEnabled(not busy)
    def add_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(self, 'Choose videos', '', 'Videos (*.mp4 *.mkv *.mov *.avi *.webm *.m4v)')
        self.add_paths(paths)
    def add_paths(self, paths):
        for name in paths:
            path = Path(name).resolve()
            if path.is_file() and path.suffix.lower() in EXTENSIONS and str(path) not in self.queue_paths:
                self.queue_paths.append(str(path))
                self.queue.addItem(path.name)
                self.queue.item(self.queue.count() - 1).setToolTip(str(path))
        if self.queue.currentRow() < 0 and self.queue.count():
            self.queue.setCurrentRow(0)
        self.update_controls()
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
    def dropEvent(self, event):
        self.add_paths([url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()])
    def select_video(self, row):
        self.cancel_mark()
        path = self.selected_path()
        if not path:
            return
        self.preview_end = None
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(path))
        self.filename.setText(Path(path).name)
        self.state, self.state_path = self.reviews.get(path, (None, None))
        self.refresh_regions()
        self.update_controls()
    def refresh_regions(self):
        events = self.state['events'] if self.state else []
        self.table.setRowCount(len(events))
        for row, item in enumerate(events):
            for col, value in enumerate([clock(item['start']), clock(item['end']), item['matched']]):
                self.table.setItem(row, col, QTableWidgetItem(value))
        self.region_count.setText(f'{len(events)} censor regions' if self.state else 'Censor regions')
        self.timeline.events = events
        self.timeline.update()
    def select_region(self):
        row = self.table.currentRow()
        if self.state and 0 <= row < len(self.state['events']):
            item = self.state['events'][row]
            self.start.setValue(item['start'])
            self.end.setValue(item['end'])
            self.player.setPosition(round(item['start'] * 1000))
    def save_review(self):
        if self.state and self.state_path:
            try:
                write_json(Path(self.state_path), self.state)
            except OSError as exc:
                QMessageBox.warning(self, 'Changes could not be saved', str(exc))
                return False
            self.reviews[self.state['video']] = (self.state, self.state_path)
        self.refresh_regions()
        self.update_controls()
        return True
    def add_region(self):
        if self.process or not self.state:
            self.set_status('Analyze this video before adding censor regions.')
            return
        start = min(self.player.position() / 1000, max(0, self.state['duration'] - .05))
        self.state['events'].append({'start': start, 'end': min(start + .5, self.state['duration']), 'matched': 'Manual region', 'kind': 'manual', 'source': 'manual'})
        self.save_review()
        self.table.selectRow(len(self.state['events']) - 1)
    def apply_region(self):
        row = self.table.currentRow()
        if self.process or not self.state or row < 0:
            return
        if not 0 <= self.start.value() < self.end.value() <= self.state['duration']:
            self.set_status('Choose start and end times inside the video, with end after start.')
            return
        self.state['events'][row].update(start=self.start.value(), end=self.end.value())
        self.save_review()
        self.table.selectRow(row)
    def remove_region(self):
        row = self.table.currentRow()
        if not self.process and self.state and row >= 0:
            del self.state['events'][row]
            self.save_review()
    def toggle_play(self):
        self.preview_end = None
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()
    def preview_region(self):
        row = self.table.currentRow()
        if self.state and row >= 0:
            item = self.state['events'][row]
            self.preview_end = (item['end'] + 1) * 1000
            self.player.setPosition(round(max(0, item['start'] - 1) * 1000))
            self.player.play()
    def position_changed(self, position):
        self.timeline.follow(position / 1000)
        if self.preview_end is not None and position >= self.preview_end:
            self.player.pause()
            self.preview_end = None
    def sync_timeline_zoom(self):
        timeline = self.timeline
        self.zoom_label.setText(f'{timeline.zoom:g}×')
        self.zoom_out.setEnabled(timeline.zoom > 1)
        self.zoom_in.setEnabled(timeline.duration > 0 and timeline.zoom < max(1, timeline.duration))
        self.timeline_pan.setEnabled(timeline.zoom > 1)
        self.timeline_pan.blockSignals(True)
        extent = timeline.duration - timeline.span
        self.timeline_pan.setRange(0, 10000 if extent else 0)
        self.timeline_pan.setValue(round(timeline.offset / extent * 10000) if extent else 0)
        self.timeline_pan.setPageStep(max(1, round(10000 / max(1, timeline.zoom-1))))
        self.timeline_pan.blockSignals(False)
    def duration_changed(self, duration):
        self.timeline.duration = duration / 1000
        self.timeline.set_view(1, 0)
    def analyze_selected(self):
        if self.selected_path():
            self.start_job({'action': 'analyze', 'video': self.selected_path(), 'config': self.config})
    def analyze_queue(self):
        self.pending = list(self.queue_paths)
        self.next_in_queue()
    def next_in_queue(self):
        if self.pending:
            path = self.pending.pop(0)
            self.queue.setCurrentRow(self.queue_paths.index(path))
            self.analyze_selected()
    def render(self):
        if not self.state or not self.save_review():
            return
        config = dict(self.config, censor_mode=self.mode.currentData())
        self.start_job({'action': 'render', 'video': self.state['video'], 'config': config, 'state': self.state})
    def setup_runtime(self):
        from setup_wizard import SetupWizard
        if SetupWizard(ROOT, self).exec() == QDialog.DialogCode.Accepted:
            self.start_job({'action': 'probe'})
    def open_settings(self):
        dialog = Settings(self, self.config, self.devices)
        dialog.download_requested.connect(lambda model: self.start_job({'action': 'download', 'model': model}))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.config = dialog.config
            self.set_status('Settings saved. Analyze again to apply detection changes.')
    def open_outputs(self):
        path = Path(self.config.get('export_path') or ROOT / 'outputs' / 'censored').expanduser()
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
    def open_result(self):
        if getattr(self, 'last_output', None):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.last_output))

    def start_job(self, job):
        if self.process:
            return
        local_path = ROOT / 'runtime.local.json'
        local = json.loads(local_path.read_text(encoding='utf-8')) if local_path.exists() else {}
        python = Path(local.get('python', str(ROOT / 'venv' / 'Scripts' / 'python.exe')))
        if not python.is_file():
            self.set_status('Python environment missing. Follow SETUP-ALPHA.md to finish setup.')
            return
        path = ROOT / 'cache' / 'jobs' / f'{uuid4().hex}.json'
        write_json(path, job)
        self.cancel_mark()
        self.job, self.job_path = job, path
        self.cancelled, self.received_result, self.buffer = False, False, ''
        self.worker_error = None
        log_path = ROOT / 'logs' / 'last-job.log'
        log_path.parent.mkdir(exist_ok=True)
        self.log = log_path.open('w', encoding='utf-8')
        environment = os.environ.copy()
        environment['PYTHONIOENCODING'] = 'utf-8'
        environment['PYTHONDONTWRITEBYTECODE'] = '1'
        for key in ('PYTHONHOME', 'PYTHONPATH', 'TCL_LIBRARY', 'TK_LIBRARY', '_MEIPASS2'):
            environment.pop(key, None)
        process = ProcessingThread([str(python), '-B', '-u', str(ROOT / 'worker.py'), str(path)], environment, self)
        self.process = process
        process.output.connect(self.read_output)
        process.finished.connect(lambda: self.job_finished(process.exit_code, None))
        process.failure.connect(self.process_error)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("%p% · estimated" if job["action"] == "analyze" else "%p%")
        self.hardware.setText({"probe": "Getting ready…", "analyze": "Analyzing", "render": "Exporting", "download": "Downloading"}[job["action"]])
        self.set_status('Checking graphics…' if job['action'] == 'probe' else 'Starting…')
        self.update_controls()
        process.start()
    def process_error(self, error):
        self.worker_error = 'Could not run the processing environment: ' + error
    def read_output(self, text):
        if not self.process:
            return
        self.log.write(text)
        self.log.flush()
        self.buffer += text
        while '\n' in self.buffer:
            line, self.buffer = self.buffer.split('\n', 1)
            if line.startswith('@@'):
                try:
                    self.message(json.loads(line[2:]))
                except (ValueError, KeyError) as exc:
                    self.worker_error = f'Unexpected processing response: {exc}'
    def message(self, data):
        kind = data['type']
        if kind == 'stage':
            self.set_status(data['message'])
            if 'percent' in data:
                self.progress.setValue(max(self.progress.value(), min(99, int(data['percent']))))
            elif self.job.get('action') == 'download':
                match = re.search(r'(\d+)%', data['message'])
                if match:
                    self.progress.setValue(min(99, int(match.group(1))))
        elif kind == 'hardware':
            self.devices = data['vulkan']
            self.hardware.setText('Ready')
            self.hardware.setToolTip('Choose your graphics card in Settings.')
            self.received_result = True
            self.set_status('Ready. Choose acceleration in Settings, then add a video.')
        elif kind == 'review':
            self.state, self.state_path = data['state'], data['state_path']
            self.reviews[self.state['video']] = (self.state, self.state_path)
            self.received_result = True
            self.refresh_regions()
            self.set_status(f'{self.state["word_count"]} words aligned · {len(self.state["events"])} censor regions · {self.state["backend"].upper()}')
            if self.state['events']:
                self.table.selectRow(0)
        elif kind == 'rendered':
            self.received_result = True
            self.last_output = data['output']
            self.open_result_btn.setEnabled(True)
            self.set_status('Export complete. Your original video is preserved.')
        elif kind == 'downloaded':
            self.received_result = True
            self.set_status(f'{data["model"]} downloaded and verified. Select it in Settings to use it.')
        elif kind == 'error':
            self.worker_error = data['message']
    def job_finished(self, code, status):
        if self.process is None:
            return
        self.log.close()
        self.process.deleteLater()
        self.process = None
        self.job_path.unlink(missing_ok=True)
        self.progress.setRange(0, 100)
        success = code == 0 and self.received_result and not self.cancelled and not self.worker_error
        self.progress.setFormat("%p%")
        self.progress.setValue(100 if success else 0)
        self.hardware.setText("Ready" if self.job.get("action") == "probe" and success else "Complete" if success else "Cancelled" if self.cancelled else "Needs attention")
        if self.cancelled:
            self.set_status('Cancelled. Original video preserved.')
            self.pending.clear()
        elif code != 0 or not self.received_result:
            self.pending.clear()
            self.set_status(self.worker_error or 'Processing stopped unexpectedly. See logs/last-job.log for details.')
        self.update_controls()
        if self.pending:
            self.next_in_queue()
    def cancel(self):
        if self.process:
            self.cancelled = True
            self.pending.clear()
            self.process.kill()  # Worker Job Object terminates its subprocesses too.
    def closeEvent(self, event):
        if self.process:
            answer = QMessageBox.question(self, 'Processing is running', 'Cancel processing and close JuicyCensor?')
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.cancel()
            self.process.waitForFinished(5000)
        self.player.stop()
        event.accept()


def main():
    if '--setup-runtime' in sys.argv:
        # Explicit command-line opt-in for unattended setup and release smoke tests.
        from bootstrap import Installer
        profile = sys.argv[sys.argv.index('--setup-runtime') + 1]
        log_path = ROOT / 'logs/setup.log'
        log_path.parent.mkdir(exist_ok=True)
        with log_path.open('a', encoding='utf-8') as log:
            def progress(message):
                log.write(message + '\n')
                log.flush()
            try:
                Installer(ROOT, progress).install(profile, '--skip-models' not in sys.argv)
            except Exception as exc:
                progress(str(exc))
                return 1
        return 0
    app = QApplication(sys.argv)
    app.setApplicationName('JuicyCensor')
    app.setWindowIcon(QIcon(str(ROOT / 'assets' / 'orange.ico')))
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('JuicyCensor.Desktop.2')
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    from bootstrap import ready
    from setup_wizard import SetupWizard
    if '--check-setup-ui' in sys.argv:
        dialog = SetupWizard(ROOT)
        dialog.show()
        QTimer.singleShot(250, app.quit)
        return app.exec()
    if not ready(ROOT):
        if '--check-startup' in sys.argv:
            write_json(ROOT / 'logs/startup-check.json', {'success': False, 'error': 'Runtime setup required', 'version': VERSION})
            return 1
        if SetupWizard(ROOT).exec() != QDialog.DialogCode.Accepted:
            return 0
    window = MainWindow()
    if '--check-startup' in sys.argv:
        timer = QTimer()
        elapsed = [0]
        def check():
            elapsed[0] += 1
            if window.process is None or elapsed[0] > 600:
                if window.process:
                    window.cancel()
                    window.process.waitForFinished(5000)
                success = window.received_result and not window.worker_error
                write_json(ROOT / 'logs' / 'startup-check.json', {
                    'success': success, 'error': window.worker_error,
                    'vulkan_devices': window.devices, 'version': VERSION})
                timer.stop()
                app.exit(0 if success else 1)
        timer.timeout.connect(check)
        timer.start(100)
        return app.exec()
    window.show()
    window.add_paths(sys.argv[1:])
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
