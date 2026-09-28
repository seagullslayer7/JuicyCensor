"""Native subtitle workspace with a bilingual grid and reviewable AI edits."""
from __future__ import annotations
import copy
import hashlib
import html
import json
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, QSizeF, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QAction
from PySide6.QtWidgets import (QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QFormLayout, QSplitter, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QLineEdit, QPlainTextEdit, QTabWidget, QCheckBox, QFileDialog, QMessageBox, QMenu,
    QDialog, QDialogButtonBox, QSpinBox, QColorDialog, QGraphicsView, QGraphicsScene,
    QGraphicsTextItem, QGraphicsDropShadowEffect, QSlider, QStyle, QScrollBar, QWidgetAction, QSizePolicy, QGridLayout, QTabBar, QStackedWidget)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem

from languages import LANGUAGES, MODELS, language_name, validate_language_model
from subtitle_document import (new_document, cue, validate_document, save_project,
    load_project, import_subtitles, export_text, quality_notes, History, timestamp)
from translation import validate_endpoint
from ui_icons import decorate_text, decorate, tool_icon
from appearance import color as theme_color


def action(text, callback, tip='', primary=False):
    button = QPushButton(text)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setToolTip(tip or text)
    button.setProperty('primary', primary)
    button.clicked.connect(callback)
    decorate_text(button, text, primary)
    return button


def command(parent, text, callback, tip):
    item = QAction(text, parent)
    item.setToolTip(tip)
    item.triggered.connect(callback)
    return item


class VideoPreview(QGraphicsView):
    def __init__(self, player):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setBackgroundBrush(QColor('#0e100e'))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMinimumSize(280, 100)
        self.video = QGraphicsVideoItem()
        self.scene().addItem(self.video)
        self.caption = QGraphicsTextItem()
        self.caption.setZValue(2)
        shadow = QGraphicsDropShadowEffect()
        shadow.setColor(QColor('#302039')); shadow.setBlurRadius(5); shadow.setOffset(0, 1)
        self.caption.setGraphicsEffect(shadow)
        self.scene().addItem(self.caption)
        self.size = QSizeF(1920, 1080)
        self.style, self.text = {}, ''
        self.video.nativeSizeChanged.connect(self.set_video_size)
        player.setVideoOutput(self.video)
        self.set_video_size(self.size)
    def set_video_size(self, size):
        if size.isEmpty(): return
        self.size = size
        self.video.setSize(size)
        self.scene().setSceneRect(0, 0, size.width(), size.height())
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.set_caption(self.text, self.style)
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
    def set_caption(self, text, style):
        self.text, self.style = text, style
        scale = self.size.height()/1080
        font = html.escape(str(style.get('font', 'Trebuchet MS')), quote=True)
        color = QColor(style.get('color', '#FF829E')).name()
        size = max(1, int(style.get('size', 38)*scale))
        self.caption.setTextWidth(self.size.width()*.90)
        self.caption.setHtml(f'<div style="text-align:center;font-family:{font};font-size:{size}px;font-weight:bold;color:{color}">{html.escape(text).replace(chr(10), "<br>")}</div>')
        self.caption.setPos(self.size.width()*.05, self.size.height()-self.caption.boundingRect().height()-style.get('margin',42)*scale)


class SmartDialog(QDialog):
    def __init__(self, parent, settings, key, combo):
        super().__init__(parent)
        self.setWindowTitle('Smart translate & refine')
        self.setMinimumWidth(620)
        layout = QVBoxLayout(self)
        heading = QLabel('Give the dialogue its voice')
        heading.setObjectName('sectionTitle'); layout.addWidget(heading)
        note = QLabel('Translate or smooth the selected lines using nearby dialogue and your scene notes.\nSuggestions stay separate until you accept them.')
        note.setWordWrap(True); note.setObjectName('muted'); layout.addWidget(note)
        form = QFormLayout(); form.setVerticalSpacing(14); layout.addLayout(form)
        self.provider = combo(); self.provider.addItem('Local AI server', 'local'); self.provider.addItem('Online AI · your API key', 'online')
        self.provider.setCurrentIndex(max(0, self.provider.findData(settings.get('provider','local'))))
        form.addRow('Process with', self.provider)
        self.endpoint = QLineEdit(settings.get('endpoint','http://localhost:11434/api/chat'))
        self.endpoint.setToolTip('Full Ollama /api/chat or compatible /v1/chat/completions endpoint.')
        form.addRow('API endpoint', self.endpoint)
        self.model = QLineEdit(settings.get('model',''))
        self.model.setPlaceholderText('Model name from your AI server or provider')
        form.addRow('Model', self.model)
        self.key = QLineEdit(key); self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText('Kept in memory for this app session only')
        form.addRow('API key', self.key)
        self.explanation = QLabel(); self.explanation.setWordWrap(True); self.explanation.setObjectName('muted')
        layout.addWidget(self.explanation)
        self.consent = QCheckBox('Send selected lines, nearby context, and scene notes to this online provider')
        layout.addWidget(self.consent)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Generate suggestions')
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
        self.provider.currentIndexChanged.connect(self.changed)
        self.changed()
    def changed(self):
        local = self.provider.currentData() == 'local'
        self.key.setEnabled(not local); self.consent.setVisible(not local); self.consent.setChecked(False)
        self.explanation.setText('Requires a running local AI server and a downloaded text model, such as in Ollama or LM Studio. This is separate from the Whisper speech model.' if local else 'Only subtitle text and scene notes are sent. Video and audio stay on your PC. Your provider may charge for requests; review its data policy.')
    def accept(self):
        try:
            local = self.provider.currentData() == 'local'
            validate_endpoint(self.endpoint.text().strip(), local)
            if not self.model.text().strip(): raise ValueError('Enter a model name.')
            if not local and (not self.key.text().strip() or not self.consent.isChecked()):
                raise ValueError('Enter your API key and confirm which text will be sent.')
        except ValueError as exc:
            QMessageBox.warning(self, 'Check AI settings', str(exc)); return
        super().accept()
    def settings(self):
        return dict(provider=self.provider.currentData(), endpoint=self.endpoint.text().strip(), model=self.model.text().strip())


class SubtitleWorkspace(QWidget):
    job_requested = Signal(dict)
    def __init__(self, host, root, combo, time_edit, timeline_type, splitter_type=QSplitter):
        super().__init__()
        self.host, self.root, self.combo = host, root, combo
        self.doc = new_document()
        self.history = History()
        self.video_path = ''
        self.autosave_path = self.root/'cache/subtitle-projects/draft.json'
        if self.autosave_path.exists():
            try: self.doc = load_project(self.autosave_path)
            except (ValueError, OSError, KeyError): pass
        self.loading, self.busy, self.active_row = False, False, -1
        self.project_path, self.preview_end = None, None
        self.resume_position = None
        self.smart_settings, self.api_key = {}, ''
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self); self.audio.setVolume(.65); self.player.setAudioOutput(self.audio)
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(8)
        toolbar = QHBoxLayout(); toolbar.setSpacing(8)
        self.import_button = command(self, 'Open subtitles', self.open_document, 'Open an SRT, VTT, ASS, or JuicyCensor subtitle project')
        self.save_button = command(self, 'Save project', self.save_document, 'Save both languages, styling, scene notes, and pending suggestions in one project')
        self.source_language = combo()
        for label, code in LANGUAGES: self.source_language.addItem(label, code)
        self.source_language.setToolTip('Language spoken in the video. Choose it explicitly for more reliable recognition.')
        self.source_language.setFixedWidth(140)
        self.source_language.currentIndexChanged.connect(self.change_source_language)
        toolbar.addWidget(QLabel('Speech')); toolbar.addWidget(self.source_language)
        self.generate_button = action('Transcribe', self.generate, 'Create subtitles in the spoken language using your local speech model', True)
        toolbar.addWidget(self.generate_button)
        layout.addLayout(toolbar)

        body = splitter_type(Qt.Orientation.Horizontal)
        self.body = body
        body.setChildrenCollapsible(False)
        self.editor_split = splitter_type(Qt.Orientation.Vertical)
        self.editor_split.setChildrenCollapsible(False)
        self.editor_split.addWidget(body)
        left = QFrame(); left.setObjectName('card'); left.setMinimumWidth(430)
        self.transcript_panel = left
        left_layout = QVBoxLayout(left); left_layout.setContentsMargins(12,12,12,12); left_layout.setSpacing(8)
        self.search = QLineEdit(); self.search.setPlaceholderText('Search source or translation…'); self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.filter_rows)
        transcript_heading = QHBoxLayout()
        label = QLabel('Transcript'); label.setObjectName('paneTitle'); transcript_heading.addWidget(label)
        transcript_heading.addWidget(self.search, 1); left_layout.addLayout(transcript_heading)
        self.table = QTableWidget(0, 5); self.table.setObjectName('subtitleTable')
        self.table.setHorizontalHeaderLabels(['#', 'Start', 'End', 'Source', 'Translation'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide(); self.table.setShowGrid(False); self.table.setAlternatingRowColors(True)
        for column in (0,1,2): self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        for column in (3,4): self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(52)
        self.table.setMinimumHeight(100)
        self.table.currentCellChanged.connect(self.select_row)
        self.table.cellDoubleClicked.connect(lambda row, col: self.play_line())
        left_layout.addWidget(self.table, 1)
        tools = QHBoxLayout()
        self.undo_button = command(self, 'Undo', self.undo, 'Undo the last subtitle edit (Ctrl+Z)')
        self.redo_button = command(self, 'Redo', self.redo, 'Redo an edit (Ctrl+Shift+Z)')
        self.add_button = action('Line', self.add_line, 'Add a subtitle at the current playback position')
        self.split_button = action('Split', self.split_line, 'Split the selected line at the playhead and source text cursor')
        self.merge_button = action('Merge', self.merge_lines, 'Merge adjacent selected subtitle lines')
        self.remove_button = action('Remove', self.remove_lines, 'Remove the selected subtitle lines; undo is available')
        for b in (self.add_button,self.split_button,self.merge_button,self.remove_button): tools.addWidget(b)
        self.count = QLabel('Open subtitles or transcribe a video to begin.'); self.count.setObjectName('muted'); self.count.setWordWrap(True)
        left_layout.addWidget(self.count)
        body.addWidget(left)

        right = QFrame(); right.setObjectName('card'); right.setMinimumWidth(430)
        self.video_panel = right
        right_layout = QVBoxLayout(right); right_layout.setContentsMargins(12,12,12,12); right_layout.setSpacing(8)
        label = QLabel('Video preview'); label.setObjectName('paneTitle'); right_layout.addWidget(label)
        self.preview = VideoPreview(self.player)
        self.preview.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        right_layout.addWidget(self.preview, 1)
        transport = QHBoxLayout()
        self.skip_seconds = 5.0
        for icon, tip, slot in [(QStyle.StandardPixmap.SP_MediaSeekBackward, 'Skip backward', lambda: self.player.setPosition(max(0,self.player.position()-round(self.skip_seconds*1000)))),
            (QStyle.StandardPixmap.SP_MediaPlay, 'Play or pause', self.toggle_play),
            (QStyle.StandardPixmap.SP_MediaSeekForward, 'Skip forward', lambda: self.player.setPosition(min(self.player.duration(),self.player.position()+round(self.skip_seconds*1000))))]:
            b = action('', slot, tip); b.setProperty('mediaIcon',icon.value); b.setIcon(host.media_icon(icon)); b.setFixedWidth(38); transport.addWidget(b)
            if tip == 'Play or pause': self.play_button = b
        self.line_play = action('Play line', self.play_line, 'Play the selected subtitle and stop at its end')
        transport.addWidget(self.line_play)
        self.clock = QLabel('00:00:00.000'); self.clock.setObjectName('muted'); self.clock.setMinimumWidth(80); transport.addWidget(self.clock); transport.addStretch()
        self.playback_popup = QMenu(self)
        self.playback_options = action('', lambda:self.playback_popup.exec(self.playback_options.mapToGlobal(self.playback_options.rect().bottomLeft())), 'Volume, playback speed, and skip interval')
        self.playback_options.setProperty('mediaIcon',QStyle.StandardPixmap.SP_MediaVolume.value)
        self.playback_options.setIcon(host.media_icon(QStyle.StandardPixmap.SP_MediaVolume)); self.playback_options.setFixedWidth(36)
        transport.addWidget(self.playback_options)
        playback_panel = QWidget(); playback_form = QFormLayout(playback_panel)
        self.volume = QSlider(Qt.Orientation.Horizontal); self.volume.setRange(0,100); self.volume.setValue(65); self.volume.setMinimumWidth(160)
        self.volume.valueChanged.connect(lambda value:self.audio.setVolume(value/100)); playback_form.addRow('Volume',self.volume)
        self.speed = type(host.skip_amount)(); self.speed.setRange(.25,4); self.speed.setDecimals(2); self.speed.setSingleStep(.25); self.speed.setValue(1); self.speed.setPrefix('×')
        self.speed.valueChanged.connect(self.player.setPlaybackRate); playback_form.addRow('Playback speed',self.speed)
        self.skip = type(host.skip_amount)(); self.skip.setRange(.1,600); self.skip.setSingleStep(1); self.skip.setValue(5); self.skip.setSuffix(' s')
        self.skip.valueChanged.connect(lambda value:setattr(self,'skip_seconds',value)); playback_form.addRow('Skip interval',self.skip)
        popup_action=QWidgetAction(self.playback_popup); popup_action.setDefaultWidget(playback_panel); self.playback_popup.addAction(popup_action)
        self.preview_track = combo(); self.preview_track.addItem('Source', 'source'); self.preview_track.addItem('Translation', 'translation'); self.preview_track.addItem('Hidden', 'hidden')
        self.preview_track.setToolTip('Which subtitle track to show during playback')
        self.preview_track.currentIndexChanged.connect(self.update_caption); transport.addWidget(self.preview_track)
        right_layout.addLayout(transport)
        self.detail_panel = QFrame(); self.detail_panel.setObjectName('card')
        detail_layout = QVBoxLayout(self.detail_panel); detail_layout.setContentsMargins(12,8,12,10); detail_layout.setSpacing(6)
        heading_row = QHBoxLayout(); heading_row.setSpacing(16)
        self.detail_navigation = QTabBar(); self.detail_navigation.setObjectName('editorTabs')
        self.detail_navigation.setExpanding(True); self.detail_navigation.setDrawBase(False)
        for name in ('Edit line', 'Suggestions', 'Style'): self.detail_navigation.addTab(name)
        self.detail_navigation.setToolTip('Edit the selected line, review suggestions, or change subtitle styling')
        self.detail_navigation_slot = QWidget(); self.detail_navigation_slot.setObjectName('reviewPage')
        navigation_layout = QHBoxLayout(self.detail_navigation_slot); navigation_layout.setContentsMargins(0,0,0,0)
        navigation_layout.addWidget(self.detail_navigation)
        heading_row.addWidget(self.detail_navigation_slot)
        self.source_heading, self.translation_heading = QLabel('Source'), QLabel('Translation')
        for label in (self.source_heading,self.translation_heading):
            label.setObjectName('paneTitle'); heading_row.addWidget(label,1)
        detail_layout.addLayout(heading_row)
        self.detail_tabs = QStackedWidget(); self.detail_tabs.setObjectName('reviewPage')
        detail_layout.addWidget(self.detail_tabs,1)
        self.detail_navigation.currentChanged.connect(self.detail_tabs.setCurrentIndex)
        self.detail_tabs.currentChanged.connect(self.change_detail_page)
        edit = QWidget(); edit.setObjectName('reviewPage'); edit_layout = QHBoxLayout(edit); edit_layout.setContentsMargins(0,0,0,0); edit_layout.setSpacing(16)
        self.timing_panel = QWidget(); self.timing_panel.setObjectName('reviewPage')
        timing = QVBoxLayout(self.timing_panel); timing.setContentsMargins(0,0,0,0); timing.setSpacing(6)
        timing_fields = QGridLayout(); timing_fields.setHorizontalSpacing(8); timing_fields.setVerticalSpacing(8)
        self.start, self.end = time_edit(), time_edit()
        for row, (name, field) in enumerate([('Start',self.start),('End',self.end)]):
            caption = QLabel(name); caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
            timing_fields.addWidget(caption,row,0); timing_fields.addWidget(field,row,1)
            field.setMinimumWidth(160); field.valueChanged.connect(self.schedule_edit)
        timing.addStretch(1); timing.addLayout(timing_fields); timing.addStretch(1)
        self.metrics = QLabel(); self.metrics.setObjectName('muted'); self.metrics.setWordWrap(True)
        self.metrics.hide(); detail_layout.addWidget(self.metrics)
        edit_layout.addWidget(self.timing_panel)
        self.source_text = QPlainTextEdit(); self.source_text.setPlaceholderText('Original dialogue')
        self.translation_text = QPlainTextEdit(); self.translation_text.setPlaceholderText('Write a translation or generate suggestions')
        for field in (self.source_text,self.translation_text):
            field.setMinimumHeight(72); field.textChanged.connect(self.schedule_edit); edit_layout.addWidget(field,1)
        self.detail_tabs.addWidget(edit)
        suggestion = QWidget(); suggestion.setObjectName('reviewPage'); suggest_layout = QVBoxLayout(suggestion); suggest_layout.setContentsMargins(0,0,0,0); suggest_layout.setSpacing(6)
        self.suggestion_text = QPlainTextEdit(); self.suggestion_text.setReadOnly(True); self.suggestion_text.setPlaceholderText('Translation and refinement suggestions appear here.')
        self.suggestion_text.setMinimumHeight(48); suggest_layout.addWidget(self.suggestion_text)
        accept_row = QHBoxLayout()
        self.accept_button = action('Accept', self.accept_suggestion, 'Use this suggestion as the translation; undo is available', True)
        self.reject_button = action('Dismiss', self.dismiss_suggestion, 'Discard this suggestion and keep your translation')
        self.accept_all_button = action('Accept all', self.accept_all, 'Apply every pending suggestion after confirmation')
        for b in (self.accept_button,self.reject_button,self.accept_all_button): accept_row.addWidget(b)
        suggest_layout.addLayout(accept_row); self.detail_tabs.addWidget(suggestion)
        style_page = QWidget(); style_page.setObjectName('reviewPage'); style_layout = QHBoxLayout(style_page); style_layout.setContentsMargins(0,0,0,0); style_layout.setSpacing(24)
        form = QFormLayout(); form.setVerticalSpacing(8); style_layout.addLayout(form,1)
        second_form = QFormLayout(); second_form.setVerticalSpacing(8); style_layout.addLayout(second_form,1)
        self.font = combo(); self.font.addItems(['Trebuchet MS','Segoe UI','Arial']); form.addRow('Font',self.font)
        self.font_size = QSpinBox(); self.font_size.setRange(12,100); self.font_size.setValue(38); form.addRow('Size at 1080p',self.font_size)
        self.color = action('Pink · #FF829E', self.choose_color, 'Choose the subtitle text color'); second_form.addRow('Text color',self.color)
        self.margin = QSpinBox(); self.margin.setRange(0,250); self.margin.setValue(42); second_form.addRow('Bottom margin',self.margin)
        self.style_hint = QLabel('ASS and video exports keep the style. SRT and VTT contain plain text. Preview uses a soft shadow; video export uses the ASS outline.')
        self.style_hint.setObjectName('muted'); self.style_hint.setWordWrap(True); style_layout.addWidget(self.style_hint,1)
        for control in (self.font,self.font_size,self.margin):
            (control.currentTextChanged if control is self.font else control.valueChanged).connect(self.change_style)
        self.detail_tabs.addWidget(style_page)
        body.addWidget(right)
        body.setSizes([600,600]); body.setStretchFactor(0,1); body.setStretchFactor(1,1)
        self.editor_split.addWidget(self.detail_panel)
        self.editor_split.setStretchFactor(0,1); self.editor_split.setStretchFactor(1,0)
        self.editor_split.setSizes([440,160])
        layout.addWidget(self.editor_split, 1)

        self.timeline = timeline_type(); self.timeline.seek.connect(lambda t:self.player.setPosition(round(t*1000)))
        self.timeline.region_selected.connect(self.select_timeline_line)
        self.timeline.region_edited.connect(self.edit_timeline_line)
        layout.addWidget(self.timeline)
        wave_tools = QHBoxLayout()
        self.wave_gain = QSlider(Qt.Orientation.Horizontal); self.wave_gain.setRange(50,400); self.wave_gain.setValue(100)
        self.wave_gain.setObjectName('waveformGain'); self.wave_gain.setFixedHeight(24)
        self.wave_gain.setFixedWidth(100); self.wave_gain.setToolTip('Waveform height only; audio volume stays unchanged')
        self.wave_gain.valueChanged.connect(self.timeline.set_gain)
        wave_label = QLabel(); wave_label.setProperty('themeGlyph','wave'); wave_label.setPixmap(tool_icon('wave').pixmap(18,18)); wave_label.setToolTip('Waveform height')
        wave_tools.addWidget(wave_label); wave_tools.addWidget(self.wave_gain, 0, Qt.AlignmentFlag.AlignVCenter)
        for name, callback, tip in [('undo',self.undo,'Undo subtitle edit · Ctrl+Z'),('redo',self.redo,'Redo subtitle edit · Ctrl+Shift+Z')]:
            control = action('',callback,tip); decorate(control,name); control.setFixedWidth(36)
            setattr(self,name+'_tool',control); wave_tools.addWidget(control)
        for plus in (False,True):
            b=action('',lambda checked=False, factor=2 if plus else .5:self.timeline.zoom_by(factor),'Zoom in' if plus else 'Zoom out')
            b.setProperty('zoomDirection',plus); b.setIcon(host.zoom_icon(plus)); b.setFixedWidth(36); wave_tools.addWidget(b)
        self.pan = QScrollBar(Qt.Orientation.Horizontal); self.pan.setRange(0,10000); self.pan.valueChanged.connect(self.timeline.pan); wave_tools.addWidget(self.pan,1)
        wave_tools.addWidget(action('Fit',lambda:self.timeline.set_view(1,0),'Show the whole video'))
        self.timeline.view_changed.connect(self.sync_pan)
        layout.addLayout(wave_tools)
        bottom = QHBoxLayout()
        self.target_language = combo()
        for label,code in LANGUAGES:
            if code != 'auto': self.target_language.addItem(label,code)
        self.target_language.setFixedWidth(140); self.target_language.currentIndexChanged.connect(self.change_target)
        bottom.addWidget(QLabel('Translate to')); bottom.addWidget(self.target_language)
        self.translate_button = action('Audio → English',self.translate,'Translate selected lines locally with Whisper. With no selection, translate all lines.')
        self.smart_button = action('Smart translate…',self.smart,'Use a local or online text model to translate and refine selected lines with context')
        bottom.addWidget(self.translate_button); bottom.addWidget(self.smart_button)
        self.context_button = command(self,'Scene notes',self.scene_notes,'Set names, terminology, tone, and scene context for Smart translate')
        bottom.addStretch()
        self.export_button = action('Export…',self.export_menu,'Save subtitle files or create a subtitled MP4 / MKV',True); bottom.addWidget(self.export_button)
        toolbar.addSpacing(12)
        toolbar.addLayout(bottom, 1)
        wave_tools.addSpacing(10)
        wave_tools.addLayout(tools)
        self.edit_timer=QTimer(self); self.edit_timer.setSingleShot(True); self.edit_timer.setInterval(550); self.edit_timer.timeout.connect(self.commit_edit)
        self.player.positionChanged.connect(self.position_changed); self.player.durationChanged.connect(self.duration_changed)
        self.player.mediaStatusChanged.connect(self.restore_position)
        self.player.playbackStateChanged.connect(lambda:self.play_button.setIcon(host.media_icon(QStyle.StandardPixmap.SP_MediaPause if self.player.playbackState()==QMediaPlayer.PlaybackState.PlayingState else QStyle.StandardPixmap.SP_MediaPlay)))
        self.player.errorOccurred.connect(lambda error,text:host.set_status('Subtitle preview: '+text))
        self.refresh(); self.set_busy(False)

    def reset_layout(self):
        self.body.setSizes([self.body.width()//2]*2)
        self.editor_split.setSizes([max(200,self.editor_split.height()-166),160])

    def change_detail_page(self, index):
        self.detail_navigation.setCurrentIndex(index)
        self.source_heading.setText('Source' if index == 0 else '')
        self.translation_heading.setText('Translation' if index == 0 else '')

    def error(self, text): QMessageBox.warning(self,'Subtitles',str(text))
    def selected_ids(self):
        rows=sorted({i.row() for i in self.table.selectionModel().selectedRows()})
        return [self.doc['cues'][r]['id'] for r in rows if not self.table.isRowHidden(r)] or [r['id'] for r in self.doc['cues']]
    def current(self):
        return self.doc['cues'][self.active_row] if 0 <= self.active_row < len(self.doc['cues']) else None
    def autosave(self):
        if self.autosave_path:
            try: save_project(self.autosave_path,self.doc)
            except (OSError,ValueError) as exc: self.host.set_status('Could not autosave subtitles: '+str(exc))
    def load_video(self,path):
        self.commit_edit(); self.autosave(); self.player.stop(); self.video_path=path
        self.resume_position = None
        # Do not open a second video decoder for an inactive workspace.
        if self.host.workspaces.currentIndex() == 1:
            self.player.setSource(QUrl.fromLocalFile(path))
        else:
            self.player.setSource(QUrl())
        self.preview_end=None
        stat=Path(path).stat(); key=hashlib.sha256(f'{path}|{stat.st_size}|{stat.st_mtime_ns}'.encode()).hexdigest()[:16]
        self.autosave_path=self.root/'cache/subtitle-projects'/f'{key}.json'
        try: self.doc=load_project(self.autosave_path) if self.autosave_path.is_file() else new_document(path)
        except (OSError,ValueError,KeyError) as exc:
            self.error('The autosaved project could not be read: '+str(exc)); self.doc=new_document(path)
        self.history=History(); self.active_row=-1; self.project_path=None; self.timeline.peaks=[]; self.timeline.duration=0; self.timeline.set_view(1,0)
        self.refresh(); self.set_busy(self.busy)
    def activate_preview(self):
        if self.video_path and self.player.source().toLocalFile() != self.video_path:
            self.player.setSource(QUrl.fromLocalFile(self.video_path))
    def clear_video(self):
        self.edit_timer.stop()
        self.deactivate_preview()
        self.video_path = ''
        self.resume_position = self.preview_end = None
        self.autosave_path = self.project_path = None
        self.doc = new_document()
        self.history = History(); self.active_row = -1
        self.timeline.peaks = []; self.timeline.position = 0; self.timeline.waveform_message = ""; self.timeline.drag = None
        self.duration_changed(0); self.clock.setText('00:00:00.000')
        self.search.clear()
        self.refresh(); self.set_busy(self.busy)
    def deactivate_preview(self):
        if not self.player.source().isEmpty():
            self.resume_position = self.player.position()
            self.player.stop()
            self.player.setSource(QUrl())
    def restore_position(self, status):
        if status == QMediaPlayer.MediaStatus.LoadedMedia and self.resume_position is not None:
            position, self.resume_position = self.resume_position, None
            self.player.setPosition(position)
    def refresh(self, row=None):
        self.loading=True
        self.source_language.setCurrentIndex(max(0,self.source_language.findData(self.doc.get('language','auto'))))
        self.target_language.setCurrentIndex(max(0,self.target_language.findData(self.doc.get('target_language','en'))))
        style=self.doc['style']; self.font.setCurrentText(style['font']); self.font_size.setValue(style['size']); self.margin.setValue(style['margin']); self.color.setText(style['color'])
        self.table.blockSignals(True); self.table.setRowCount(len(self.doc['cues']))
        for index,item in enumerate(self.doc['cues']):
            notes=quality_notes(item,self.doc['cues'][index-1] if index else None)
            values=[str(index+1),timestamp(item['start']).replace(',','.'),timestamp(item['end']).replace(',','.'),item['source'],item.get('translation','') or ('Review suggestion →' if item.get('suggestion') else '')]
            for col,value in enumerate(values):
                cell=QTableWidgetItem(value); cell.setToolTip(notes or value)
                if col<3: cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col==4 and item.get('suggestion'): cell.setForeground(theme_color('accent_text'))
                self.table.setItem(index,col,cell)
        self.table.blockSignals(False)
        self.active_row=-1
        self.loading=False
        if self.doc['cues']:
            self.table.selectRow(min(max(0,row if row is not None else 0),len(self.doc['cues'])-1))
            self.select_row(self.table.currentRow(),0,-1,-1)
        else: self.select_row(-1,0,-1,-1)
        self.timeline.events=self.doc['cues']; self.timeline.update(); self.filter_rows(); self.refresh_count(); self.update_caption()
    def refresh_count(self):
        cues=self.doc['cues']; translated=sum(bool(c.get('translation','').strip()) for c in cues); pending=sum(bool(c.get('suggestion')) for c in cues)
        self.count.setText(f'{len(cues)} lines  ·  {translated} translated  ·  {pending} suggestions' if cues else 'Open subtitles or transcribe a video to begin.')
        self.detail_navigation.setTabText(1,f'Suggestions ({pending})' if pending else 'Suggestions')
        # Match the navigation and timing columns, even when the suggestion count grows.
        tab_width = self.detail_navigation.sizeHint().width()
        width = max(240, tab_width)
        self.detail_navigation.setFixedWidth(width)
        self.detail_navigation_slot.setFixedWidth(width); self.timing_panel.setFixedWidth(width)
    def filter_rows(self):
        query=self.search.text().casefold().strip()
        for row,item in enumerate(self.doc['cues']): self.table.setRowHidden(row, bool(query) and query not in (item['source']+' '+item.get('translation','')).casefold())
    def select_row(self,row,col,old_row,old_col):
        if self.loading:return
        if row != self.active_row and self.current() and not self.commit_edit(refresh=False):
            self.table.blockSignals(True); self.table.selectRow(self.active_row); self.table.blockSignals(False)
            self.host.set_status('End must be after Start. Correct the timing before selecting another line.')
            return
        self.active_row=row; item=self.current(); self.loading=True
        self.start.setValue(item['start'] if item else 0); self.end.setValue(item['end'] if item else 0)
        self.source_text.setPlainText(item['source'] if item else ''); self.translation_text.setPlainText(item.get('translation','') if item else '')
        self.suggestion_text.setPlainText(item.get('suggestion','') if item else '')
        self.timeline.selected_index = row; self.timeline.update()
        self.loading=False; self.update_metrics(); self.update_caption()
    def select_timeline_line(self, index):
        if self.busy or not 0 <= index < len(self.doc['cues']): return
        if not self.commit_edit(): return
        self.player.pause()
        self.search.clear(); self.table.selectRow(index)
        self.table.scrollToItem(self.table.item(index,0))

    def edit_timeline_line(self, index, start, end):
        if self.busy or not 0 <= index < len(self.doc['cues']): return
        if not 0 <= start < end <= self.timeline.duration or not self.commit_edit(): return
        self.history.record(self.doc)
        item = self.doc['cues'][index]; item.update(start=start,end=end)
        selected_id = item['id']
        self.doc['cues'].sort(key=lambda item:item['start'])
        row = next(i for i,item in enumerate(self.doc['cues']) if item['id']==selected_id)
        self.refresh(row); self.autosave()

    def schedule_edit(self,*_):
        if not self.loading and not self.busy and self.current(): self.edit_timer.start()
    def commit_edit(self, refresh=True):
        self.edit_timer.stop(); item=self.current()
        if self.loading or not item:return True
        start,end=self.start.value(),self.end.value()
        if end<=start:
            self.metrics.setText('End must be after Start. This edit has not been saved.'); return False
        values=dict(start=start,end=end,source=self.source_text.toPlainText(),translation=self.translation_text.toPlainText())
        if any(item.get(k)!=v for k,v in values.items()):
            self.history.record(self.doc); item.update(values)
            for col,value in [(1,timestamp(start).replace(',','.')),(2,timestamp(end).replace(',','.')),(3,item['source']),(4,item['translation'])]:
                self.table.item(self.active_row,col).setText(value)
            self.autosave(); self.timeline.update(); self.refresh_count(); self.update_caption()
        self.update_metrics(); return True
    def update_metrics(self):
        item=self.current()
        self.metrics.setVisible(bool(item))
        if item:
            text=item.get('translation') or item['source']; duration=item['end']-item['start']
            notes=quality_notes(item,self.doc['cues'][self.active_row-1] if self.active_row else None)
            self.metrics.setText(f'{duration:.2f} s  ·  {len(text.replace(chr(10),""))/duration:.1f} characters/s'+('  ·  '+notes if notes else ''))
        else:self.metrics.clear()
    def record_change(self):
        self.commit_edit(); self.history.record(self.doc)
    def undo(self):
        if self.busy:return
        self.commit_edit(); self.doc=self.history.undo(self.doc); self.refresh(self.active_row); self.autosave()
    def redo(self):
        if self.busy:return
        self.doc=self.history.redo(self.doc); self.refresh(self.active_row); self.autosave()
    def open_document(self):
        path,_=QFileDialog.getOpenFileName(self,'Open subtitles or a project','','Subtitles (*.srt *.vtt *.ass *.ssa);;JuicyCensor projects (*.juice.json)')
        if not path:return
        try:
            doc=load_project(path) if path.endswith('.json') else import_subtitles(path)
            self.commit_edit(); self.history.record(self.doc)
            if path.endswith('.json') and doc.get('video') and doc['video'] != self.video_path:
                if not Path(doc['video']).is_file(): raise ValueError('The project video has moved. Add the video first and import its subtitle file, or restore the original video path.')
                self.host.add_paths([doc['video']]); self.host.queue.setCurrentRow(self.host.queue_paths.index(doc['video']))
            doc['video']=self.video_path; self.doc=doc; self.refresh(); self.autosave()
            self.project_path=Path(path) if path.endswith('.json') else None
            self.host.set_status(doc.get('import_note','Subtitles loaded. The original file is preserved.'))
        except (ValueError,OSError,KeyError) as exc:self.error(exc)
    def save_document(self):
        if not self.commit_edit():return
        path,_=QFileDialog.getSaveFileName(self,'Save subtitle project',str(self.project_path or self.root/'outputs'/'subtitles.juice.json'),'JuicyCensor project (*.juice.json)')
        if not path:return
        if not path.endswith('.juice.json'):path+='.juice.json'
        try:save_project(path,self.doc); self.project_path=Path(path); self.host.set_status('Subtitle project saved with both languages and suggestions.')
        except (OSError,ValueError) as exc:self.error(exc)
    def add_line(self):
        self.record_change(); start=self.player.position()/1000; end=start+2
        if self.player.duration():end=min(end,self.player.duration()/1000)
        if end<=start:return
        item=cue(start,end); self.doc['cues'].append(item); self.doc['cues'].sort(key=lambda c:c['start'])
        self.refresh(self.doc['cues'].index(item)); self.autosave(); self.source_text.setFocus()
    def split_line(self):
        if not self.commit_edit():return
        item=self.current(); position=self.player.position()/1000
        if not item or not item['start']<position<item['end']:
            self.error('Place the playhead inside the selected subtitle, then position the source text cursor where it should split.');return
        cursor=self.source_text.textCursor().position(); text=item['source']
        if not 0<cursor<len(text):self.error('Place the source text cursor between the words to split.');return
        self.history.record(self.doc); second=cue(position,item['end'],text[cursor:].lstrip())
        item['end']=position; item['source']=text[:cursor].rstrip(); item['suggestion']=''
        # Keep existing target text on the first line, explicitly flagging manual redistribution.
        self.doc['cues'].insert(self.active_row+1,second); self.refresh(self.active_row); self.autosave()
        self.host.set_status('Line split. Review how the translation should be divided between the two lines.')
    def merge_lines(self):
        self.commit_edit(); rows=sorted(i.row() for i in self.table.selectionModel().selectedRows())
        if len(rows)<2 or rows!=list(range(rows[0],rows[-1]+1)):
            self.error('Select two or more adjacent lines to merge.');return
        self.history.record(self.doc); items=self.doc['cues'][rows[0]:rows[-1]+1]
        merged=cue(min(i['start'] for i in items),max(i['end'] for i in items),'\n'.join(i['source'] for i in items),'\n'.join(i.get('translation','') for i in items).strip())
        self.doc['cues'][rows[0]:rows[-1]+1]=[merged];self.refresh(rows[0]);self.autosave()
    def remove_lines(self):
        ids={self.doc['cues'][i.row()]['id'] for i in self.table.selectionModel().selectedRows()}
        if not ids:return
        self.record_change(); self.doc['cues']=[c for c in self.doc['cues'] if c['id'] not in ids];self.refresh(self.active_row);self.autosave()
    def accept_suggestion(self):
        item=self.current()
        if item and item.get('suggestion'):
            self.record_change(); item['translation']=item['suggestion'];item['suggestion']='';self.refresh(self.active_row);self.autosave()
    def dismiss_suggestion(self):
        item=self.current()
        if item and item.get('suggestion'):
            self.record_change();item['suggestion']='';self.refresh(self.active_row);self.autosave()
    def accept_all(self):
        count=sum(bool(c.get('suggestion')) for c in self.doc['cues'])
        if not count:return
        if QMessageBox.question(self,'Accept suggestions',f'Apply {count} suggestions to the translation? You can undo this.') != QMessageBox.StandardButton.Yes:return
        self.record_change()
        for item in self.doc['cues']:
            if item.get('suggestion'):item['translation']=item['suggestion'];item['suggestion']=''
        self.refresh(self.active_row);self.autosave()
    def change_target(self):
        if not self.loading:
            self.record_change();self.doc['target_language']=self.target_language.currentData();self.autosave()
    def change_source_language(self):
        if not self.loading:
            self.record_change(); self.doc['language']=self.source_language.currentData(); self.autosave()
    def choose_color(self):
        color=QColorDialog.getColor(QColor(self.doc['style']['color']),self,'Subtitle text color')
        if color.isValid():
            self.record_change();self.doc['style']['color']=color.name();self.color.setText(color.name());self.autosave();self.update_caption()
    def change_style(self,*_):
        if self.loading:return
        self.record_change();self.doc['style'].update(font=self.font.currentText(),size=self.font_size.value(),margin=self.margin.value());self.autosave();self.update_caption()
    def scene_notes(self):
        dialog=QDialog(self);dialog.setWindowTitle('Scene notes');dialog.resize(560,320);layout=QVBoxLayout(dialog)
        label=QLabel('Names, terminology, tone, and context for Smart translate.\nThese notes are included with AI translation requests.');label.setWordWrap(True);layout.addWidget(label)
        text=QPlainTextEdit(self.doc.get('context',''));text.setPlaceholderText('Example: A relaxed conversation. Keep names unchanged. Use natural, informal English.');layout.addWidget(text)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
        if dialog.exec():self.record_change();self.doc['context']=text.toPlainText();self.autosave()
    def generate(self):
        if self.doc['cues'] and QMessageBox.question(self,'Transcribe again','Replace the current subtitle project with a new transcript? The previous version will be available with Undo.')!=QMessageBox.StandardButton.Yes:return
        dialog=QDialog(self);dialog.setWindowTitle('Transcribe video');layout=QVBoxLayout(dialog);form=QFormLayout();layout.addLayout(form)
        model=self.combo();model.addItems(list(MODELS));model.setCurrentText(self.host.config.get('subtitle_model','large-v3'));form.addRow('Speech model',model)
        quiet=QCheckBox('Quiet speech / whispers');quiet.setChecked(self.host.config.get('subtitle_quiet',False));form.addRow(quiet)
        note=QLabel('Uses the acceleration selected in Settings. A missing NVIDIA/CPU model downloads on first use; Vulkan models must be downloaded in Settings.\n\nQuiet mode skips voice-activity filtering on NVIDIA/CPU. Review pauses for invented speech. Vulkan already runs without this filter.');note.setWordWrap(True);note.setMaximumWidth(520);note.setObjectName('muted');layout.addWidget(note)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Transcribe locally');buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
        if dialog.exec():
            try:validate_language_model(self.source_language.currentData(),model.currentText())
            except ValueError as exc:self.error(exc);return
            self.host.config.update(subtitle_model=model.currentText(),subtitle_vulkan_model=model.currentText(),subtitle_quiet=quiet.isChecked())
            self.submit('subtitle_transcribe')
    def translate(self):
        if self.doc.get('target_language')!='en':self.error('Local Whisper audio translation outputs English. Use Smart translate for other target languages.');return
        ids=self.selected_ids()
        if QMessageBox.question(self,'Translate audio locally',f'Translate {len(ids)} selected lines into English using Whisper? Suggestions will be saved for review. A missing speech model may need to download.')==QMessageBox.StandardButton.Yes:
            self.submit('subtitle_translate',ids=ids)
    def smart(self):
        if not self.commit_edit():return
        dialog=SmartDialog(self,self.smart_settings,self.api_key,self.combo)
        if dialog.exec():
            self.smart_settings=dialog.settings();self.api_key=dialog.key.text()
            self.submit('subtitle_smart',ids=self.selected_ids(),settings=self.smart_settings)
    def submit(self,action_name,**values):
        if self.busy or not self.commit_edit():return
        if action_name == 'subtitle_smart' and not self.selected_ids(): return
        config=dict(self.host.config,subtitle_language=self.source_language.currentData())
        job=dict(action=action_name,video=self.video_path,config=config,document=copy.deepcopy(self.doc),**values)
        self.job_requested.emit(job)
    def receive(self,data):
        if data['type']=='subtitle_document':
            self.history.record(self.doc);self.doc=data['document'];self.refresh();self.autosave()
            self.host.set_status(f'{len(self.doc["cues"])} subtitle lines · {language_name(self.doc["language"])}. Review the transcript before translating.')
        elif data['type']=='subtitle_suggestions':
            self.history.record(self.doc)
            for item in self.doc['cues']:
                if item['id'] in data['suggestions']:item['suggestion']=data['suggestions'][item['id']]
            self.refresh(self.active_row);self.autosave();self.detail_tabs.setCurrentIndex(1)
            self.host.set_status(f'{len(data["suggestions"])} suggestions ready. Review and accept the ones you want.')
        elif data['type']=='subtitle_waveform':
            self.timeline.peaks=data['peaks'];self.timeline.duration=data['duration'];self.timeline.update()
            self.host.set_status('Waveform ready. Scroll to zoom and click to seek.')
    def set_busy(self,busy):
        self.busy=busy
        for widget in (self.import_button,self.save_button,self.table,self.detail_tabs,self.undo_button,self.redo_button,self.add_button,self.split_button,self.merge_button,self.remove_button,self.target_language,self.source_language,self.context_button):widget.setEnabled(not busy)
        self.generate_button.setEnabled(not busy and bool(self.video_path))
        self.undo_tool.setEnabled(not busy); self.redo_tool.setEnabled(not busy)
        self.timeline.editable = not busy
        if busy: self.timeline.drag = None
        self.translate_button.setEnabled(not busy and bool(self.doc['cues']) and bool(self.video_path))
        for widget in (self.smart_button,self.export_button):widget.setEnabled(not busy and bool(self.doc['cues']))
        self.host.sync_menu_actions()
    def toggle_play(self):
        if self.player.playbackState()==QMediaPlayer.PlaybackState.PlayingState:self.player.pause()
        else:self.preview_end=None;self.player.play()
    def play_line(self):
        item=self.current()
        if item:self.preview_end=item['end'];self.player.setPosition(round(item['start']*1000));self.player.play()
    def position_changed(self,ms):
        seconds=ms/1000;self.clock.setText(timestamp(seconds).replace(',','.'));self.timeline.follow(seconds);self.update_caption()
        if self.preview_end is not None and seconds>=self.preview_end:self.player.pause();self.preview_end=None
    def duration_changed(self,ms):
        if not ms and self.video_path: return  # Deactivating a preview must keep its waveform and zoom.
        duration = ms/1000
        if abs(self.timeline.duration-duration) > .1:
            self.timeline.duration=duration; self.timeline.set_view(1,0)
    def update_caption(self,*_):
        now=self.player.position()/1000;track=self.preview_track.currentData()
        text='\n'.join(c.get(track,'') for c in self.doc['cues'] if c['start']<=now<c['end']) if track!='hidden' else ''
        self.preview.set_caption(text,self.doc['style'])
    def sync_pan(self):
        self.pan.blockSignals(True);self.pan.setValue(round(self.timeline.offset/max(.001,self.timeline.duration-self.timeline.span)*10000));self.pan.setEnabled(self.timeline.zoom>1);self.pan.blockSignals(False)
    def export_menu(self):
        if not self.commit_edit():return
        menu=QMenu(self)
        for track,label in [('source','Source'),('translation','Translation')]:
            sub=menu.addMenu(label)
            for fmt in ('srt','vtt','ass'):
                sub.addAction(fmt.upper()+' subtitle file',lambda checked=False,f=fmt,t=track:self.export_file(f,t))
            sub.addSeparator()
            sub.addAction('MP4 · permanent subtitles',lambda checked=False,t=track:self.export_movie('mp4',t))
            sub.addAction('MKV · switchable subtitles',lambda checked=False,t=track:self.export_movie('mkv',t))
        menu.exec(self.export_button.mapToGlobal(self.export_button.rect().bottomLeft()))
    def export_file(self,fmt,track):
        try:text=export_text(self.doc,fmt,track)
        except ValueError as exc:self.error(exc);return
        path,_=QFileDialog.getSaveFileName(self,'Export subtitle file',str(self.root/'outputs'/f'subtitles.{track}.{fmt}'),f'{fmt.upper()} (*.{fmt})')
        if path:
            path=Path(path)
            if path.suffix.lower()!='.'+fmt:path=Path(str(path)+'.'+fmt)
            try:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8-sig');self.host.set_status('Subtitle file exported.')
            except OSError as exc:self.error(exc)
    def export_movie(self,fmt,track):
        if not self.video_path:self.error('Add the matching video before exporting a video file.');return
        try:export_text(self.doc,'ass',track)
        except ValueError as exc:self.error(exc);return
        path,_=QFileDialog.getSaveFileName(self,'Export subtitled video',str(self.root/'outputs'/f'{Path(self.video_path).stem}-subtitled.{fmt}'),f'{fmt.upper()} (*.{fmt})')
        if not path:return
        if not path.lower().endswith('.'+fmt):path+='.'+fmt
        if Path(path).exists():self.error('Choose a new filename. Subtitle video exports do not replace existing files.');return
        self.submit('subtitle_export',output=path,format=fmt,track=track)
