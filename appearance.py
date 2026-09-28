"""Local appearance preferences, semantic colors, and a live theme editor."""
from __future__ import annotations
import copy
import json
import math
from pathlib import Path
import re
from uuid import uuid4

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QPushButton, QSlider, QComboBox, QColorDialog, QFrame, QDialogButtonBox, QInputDialog,
    QMessageBox, QScrollArea, QWidget)


DEFAULT = dict(background='#191710', accent='#f4a339', highlight='#425432',
               waveform='#89bf62', progress='#398b38', saturation=100,
               brightness=0, highlight_strength=100, density='comfortable', corners=10)
PRESETS = {
    'Orange grove': dict(DEFAULT),
    'Midnight': dict(DEFAULT, background='#101824', accent='#68baff', highlight='#284a6a', waveform='#64d4c9'),
    'Berry': dict(DEFAULT, background='#21151e', accent='#f18ebc', highlight='#693b56', waveform='#d6a2eb'),
    'Graphite': dict(DEFAULT, background='#191b20', accent='#bdc9db', highlight='#434d60', waveform='#8bbcb4'),
}
COLOR_FIELDS = ('background', 'accent', 'highlight', 'waveform', 'progress')
RANGES = {'saturation': (0,150), 'brightness': (-30,40), 'highlight_strength': (40,150), 'corners': (0,14)}


def normalize(raw):
    raw = raw if isinstance(raw, dict) else {}
    value = dict(DEFAULT)
    for key in COLOR_FIELDS:
        if isinstance(raw.get(key), str) and re.fullmatch(r'#[0-9a-fA-F]{6}', raw[key]): value[key] = raw[key].lower()
    for key,(low,high) in RANGES.items():
        number = raw.get(key)
        if isinstance(number,(int,float)) and not isinstance(number,bool) and math.isfinite(number):
            value[key] = max(low,min(high,round(number)))
    if raw.get('density') in ('compact','comfortable'): value['density'] = raw['density']
    return value


def normalize_document(raw):
    raw = raw if isinstance(raw,dict) else {}
    presets = []
    candidates = raw.get('presets',[])
    for item in (candidates[:20] if isinstance(candidates,list) else []):
        if not isinstance(item,dict) or not isinstance(item.get('name'),str): continue
        name = item['name'].strip()[:40]
        if not name or name in PRESETS or any(p['name']==name for p in presets): continue
        presets.append(dict(name=name,settings=normalize(item.get('settings'))))
    return dict(schema=1, settings=normalize(raw.get('settings')), presets=presets)


def load_preferences(path):
    try: return normalize_document(json.loads(Path(path).read_text(encoding='utf-8')))
    except (OSError,ValueError,TypeError): return normalize_document({})


def save_preferences(path, document):
    path = Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    temporary = path.with_name(path.name+'.'+uuid4().hex+'.tmp')
    try:
        temporary.write_text(json.dumps(normalize_document(document),indent=2),encoding='utf-8')
        temporary.replace(path)
    finally: temporary.unlink(missing_ok=True)


def mix(a,b,amount):
    a,b = QColor(a),QColor(b)
    return QColor.fromRgbF(*(a.getRgbF()[i]*(1-amount)+b.getRgbF()[i]*amount for i in range(3)))


def luminance(c):
    channels = [v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in QColor(c).getRgbF()[:3]]
    return sum(a*b for a,b in zip(channels,(.2126,.7152,.0722)))


def contrast(a,b):
    x,y = sorted((luminance(a),luminance(b))); return (y+.05)/(x+.05)


def text_on(background):
    candidates = ('#11130f','#f7f8f2')
    best = max(candidates,key=lambda c:contrast(c,background))
    if contrast(best,background)<4.5: best=max(('#000000','#ffffff'),key=lambda c:contrast(c,background))
    return QColor(best)


def readable(foreground,background,minimum=4.5):
    original = QColor(foreground); target = text_on(background)
    for amount in range(0,101,5):
        value = mix(original,target,amount/100)
        if contrast(value,background)>=minimum: return value
    return target


def palette(settings):
    s=normalize(settings)
    def saturated(value):
        c=QColor(value); h,sat,v,_=c.getHsvF()
        return QColor.fromHsvF(max(0,h),min(1,sat*s['saturation']/100),v)
    def shifted(value):
        value=saturated(value)
        return mix(value,'#ffffff' if s['brightness']>=0 else '#000000',abs(s['brightness'])/100)
    bg=shifted(s['background'])
    default_base = s['background']==DEFAULT['background']
    surface=shifted('#21251e') if default_base else mix(bg,text_on(bg),.045)
    field=shifted('#191f17') if default_base else mix(bg,'#000000',.08)
    raised=shifted('#30382a') if default_base else mix(surface,text_on(surface),.06)
    canvas=mix(bg,'#000000',.18)
    accent=saturated(s['accent']); highlight=saturated(s['highlight'])
    strength=s['highlight_strength']/100
    highlight=mix(surface,highlight,strength) if strength<=1 else mix(highlight,text_on(surface),(strength-1)*.32)
    progress=saturated(s['progress']); wave=readable(saturated(s['waveform']),canvas,3)
    fg=text_on(bg)
    on_accent=text_on(accent)
    accent_hover=mix(accent,'#000000' if luminance(on_accent)>.5 else '#ffffff',.12)
    block=mix(canvas,highlight,.4);selected_block=mix(canvas,highlight,.85)
    p=dict(background=bg,surface=surface,field=field,raised=raised,
        alternate=mix(surface,fg,.025),hover=mix(raised,fg,.06),pressed=mix(raised,fg,.12),
        border=mix(surface,fg,.17),border_hover=mix(surface,fg,.32),muted=readable(mix(surface,fg,.55),surface),
        text=fg,heading=fg,disabled=mix(surface,fg,.34),disabled_bg=mix(surface,bg,.4),
        accent=accent,accent_hover=accent_hover,accent_text=readable(accent,surface),
        on_accent=on_accent,highlight=highlight,on_highlight=text_on(highlight),
        progress=progress,on_progress=text_on(progress),progress_bg=mix(surface,progress,.2),
        success=readable(progress,surface),success_bg=mix(surface,progress,.16),
        canvas=canvas,wave=wave,block=block,selected_block=selected_block,
        on_block=text_on(block),on_selected_block=text_on(selected_block),
        wave_border=readable(wave,canvas,3),playhead=text_on(canvas),timeline_text=text_on(canvas),
        timeline_muted=readable(mix(canvas,text_on(canvas),.6),canvas),
        header=mix(surface,fg,.045),command=mix(bg,'#000000',.13),sidebar=mix(bg,'#000000',.2))
    return {key:value.name() for key,value in p.items()}


_current = palette(DEFAULT)
def color(role): return QColor(_current[role])


# Map existing widget styling to shared roles; geometry remains owned by the UI.
ROLE_COLORS = {
    'background': '#191710 #181a16', 'surface': '#242219 #21251e #20251d',
    'sidebar': '#12150f #11150f', 'command': '#161b14',
    'field': '#191f17 #2d3021 #24291b', 'raised': '#353a27 #30382a #282d1e #252e20 #232a1f #232a1e #232c1e',
    'hover': '#465031 #3a472f #2c3625 #35402d', 'pressed': '#536039',
    'border': '#383e28 #44402c #51563a #3c422c #41432d #414a2c #383c29 #30392a #38422f #46513a #353e2d #35422c #35402e #3a4432 #35402e',
    'border_hover': '#677851 #778651 #546141 #586346 #64502d',
    'text': '#fff4dc #eeece2 #fff0d5 #eaeede #f5f7ee',
    'muted': '#b5b79a #a6ad9b #c5cfb6 #d1cfaf #acb69e #aeb9a1',
    'disabled': '#858971 #777f6b #747b6a', 'disabled_bg': '#25291d #242a20',
    'accent': '#ff9f24 #f4a339',
    'accent_text': '#ffac35 #ffbf63 #ffc563 #ffb94f #d89b47 #be8e43 #ffc069 #ffbd60 #ffb647',
    'accent_hover': '#ffbc5c #ffd18a', 'on_accent': '#261b0a #241b0d',
    'highlight': '#42462d #525735 #626b40 #434c2b #3b492d #3d4c2f #425432 #455632 #252f20',
    'on_highlight': '#fff #fff6e4 #fff4dd', 'alternate': '#262d21',
    'header': '#353824 #303b27',
    'success_bg': '#31552a #26311f #342b1a', 'success': '#79b84b #c9dcb1 #537044 #445337',
    'progress': '#398b38', 'progress_bg': '#20321c', 'wave_border': '#7a874e',
}
HEX_ROLES={value:role for role,values in ROLE_COLORS.items() for value in values.split()}


def apply_theme(app, base_style, settings):
    global _current
    settings=normalize(settings); _current=palette(settings)
    css=re.sub(r'#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b',lambda m:_current[HEX_ROLES[m[0].lower()]] if m[0].lower() in HEX_ROLES else m[0],base_style)
    corners=settings['corners']; button_radius=round(corners*.6)
    padding='6px 9px' if settings['density']=='compact' else '8px 11px'
    css+=f'''
QFrame#card {{ border-radius: {corners}px; }}
QPushButton {{ border-radius: {button_radius}px; padding: {padding}; }}
QComboBox, QLineEdit, QPlainTextEdit, QDoubleSpinBox, QSpinBox {{ border-radius: {button_radius}px; }}
QWidget#appearancePage {{ background: transparent; }}
QPushButton#colorSwatch {{ text-align: left; font-family: 'Consolas'; font-weight: 400; }}
QLabel#appearanceNote {{ color: {_current['muted']}; font-size: 11px; }}
QTabBar#editorTabs {{ background: {_current['surface']}; }}
QTabBar#editorTabs::tab {{ padding: 6px 10px; }}
QProgressBar {{ color: {_current['on_progress']}; }}
QCheckBox {{ spacing: 8px; }}
QSlider#appearanceSlider::groove:horizontal {{ height: 4px; border-radius: 2px; }}
QSlider#appearanceSlider::handle:horizontal {{ width: 10px; margin: -4px 0; border-radius: 6px; }}
'''
    if settings['density']=='compact':
        css+='QTableWidget#subtitleTable::item { padding: 5px 8px; } QMenu::item { padding: 6px 16px; }'
    qpal=app.palette()
    for role,key in ((QPalette.ColorRole.Window,'background'),(QPalette.ColorRole.Base,'field'),
        (QPalette.ColorRole.AlternateBase,'alternate'),(QPalette.ColorRole.WindowText,'text'),
        (QPalette.ColorRole.Text,'text'),(QPalette.ColorRole.ButtonText,'text'),
        (QPalette.ColorRole.Button,'raised'),(QPalette.ColorRole.Highlight,'highlight'),
        (QPalette.ColorRole.HighlightedText,'on_highlight'),(QPalette.ColorRole.PlaceholderText,'muted'),
        (QPalette.ColorRole.ToolTipBase,'surface'),(QPalette.ColorRole.ToolTipText,'text')):
        qpal.setColor(role,color(key))
    app.setPalette(qpal); app.setStyleSheet(css)
    return settings


def swatch(value):
    pix=QPixmap(36,36);pix.fill(Qt.GlobalColor.transparent);pix.setDevicePixelRatio(2)
    p=QPainter(pix);p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(color('border_hover'));p.setBrush(QColor(value));p.drawRoundedRect(1,1,16,16,4,4);p.end()
    return QIcon(pix)


class AppearanceDialog(QDialog):
    """Modeless previews, with explicit Save or complete rollback on Cancel."""
    def __init__(self, host):
        super().__init__(host)
        self.host=host
        self.original=copy.deepcopy(host.appearance_document)
        self.settings=dict(self.original['settings']);self.custom=copy.deepcopy(self.original['presets'])
        self.saved=False;self.updating=False
        self.setWindowTitle('Appearance'); self.resize(480,650);self.setMinimumSize(440,540)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        combo_type=type(host.subtitles.source_language)
        layout=QVBoxLayout(self);layout.setContentsMargins(18,16,18,16);layout.setSpacing(12)
        heading=QLabel('Make it your kind of juicy');heading.setObjectName('sectionTitle');layout.addWidget(heading)
        note=QLabel('Preview changes as you go. Save to keep this look.');note.setObjectName('appearanceNote');layout.addWidget(note)
        presets=QHBoxLayout();self.preset=combo_type();self.preset.setToolTip('Start with a palette, then adjust individual colors and controls')
        presets.addWidget(self.preset,1)
        self.save_preset=QPushButton('Save preset…');self.save_preset.setToolTip('Name this look so you can return to it later');presets.addWidget(self.save_preset)
        layout.addLayout(presets)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame)
        page=QWidget();page.setObjectName('appearancePage');form=QFormLayout(page);form.setContentsMargins(0,4,8,6);form.setVerticalSpacing(10)
        form.setHorizontalSpacing(16)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        scroll.setWidget(page);layout.addWidget(scroll,1)
        self.color_buttons={}
        for key,label,tip in (
            ('background','Background','Base color for the workspace. Panels and borders adapt to it.'),
            ('accent','Accent','Action buttons, active tabs, focus borders, and icons.'),
            ('highlight','Selection','Selected table rows, tabs, and timing blocks.'),
            ('waveform','Waveform','Audio peaks in both workspaces. Visibility adjusts for contrast.'),
            ('progress','Progress','The processing progress bar and Ready indicator.')):
            button=QPushButton();button.setObjectName('colorSwatch');button.setToolTip(tip)
            button.clicked.connect(lambda checked=False,k=key:self.pick_color(k));self.color_buttons[key]=button;form.addRow(label,button)
        self.sliders={};self.values={}
        for key,label,tip in (
            ('saturation','Saturation','Overall color intensity: 0% is monochrome; 100% preserves your chosen colors.'),
            ('brightness','Brightness','Brighten or darken backgrounds and panels without changing the video.'),
            ('highlight_strength','Highlight strength','Make selected rows and timing blocks quieter or more prominent.'),
            ('corners','Corner softness','Change the rounding of cards, buttons, and fields.')):
            row=QHBoxLayout();slider=QSlider(Qt.Orientation.Horizontal);slider.setObjectName('appearanceSlider');slider.setFixedHeight(24)
            slider.setRange(*RANGES[key]);slider.setToolTip(tip);slider.setAccessibleName(label)
            value=QLabel();value.setFixedWidth(44);value.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(slider,1);row.addWidget(value);form.addRow(label,row)
            self.sliders[key]=slider;self.values[key]=value
            slider.valueChanged.connect(lambda v,k=key:self.change(k,v))
        self.density=combo_type();self.density.addItem('Comfortable','comfortable');self.density.addItem('Compact','compact')
        self.density.setToolTip('Compact controls and transcript rows leave more room for your video.')
        form.addRow('Spacing',self.density);self.density.currentIndexChanged.connect(lambda:self.change('density',self.density.currentData()))
        foot=QLabel('Text contrast adjusts automatically. These controls change the app’s appearance; subtitle styling stays in Style.')
        foot.setObjectName('appearanceNote');foot.setWordWrap(True);layout.addWidget(foot)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel|QDialogButtonBox.StandardButton.RestoreDefaults)
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).setText('Reset to Orange')
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(self.reset)
        buttons.button(QDialogButtonBox.StandardButton.Save).setProperty('primary',True)
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        self.preview_timer=QTimer(self);self.preview_timer.setSingleShot(True);self.preview_timer.setInterval(35);self.preview_timer.timeout.connect(self.preview)
        self.save_preset.clicked.connect(self.add_preset);self.preset.currentIndexChanged.connect(self.choose_preset)
        self.finished.connect(self.finish)
        self.sync()

    def sync(self, preferred=None):
        self.updating=True
        self.preset.clear();self.preset.addItem('Custom',None)
        for name,settings in PRESETS.items():self.preset.addItem(name,dict(settings))
        for item in self.custom:self.preset.addItem(item['name'],dict(item['settings']))
        match=next((i for i in range(1,self.preset.count()) if self.preset.itemData(i)==self.settings and self.preset.itemText(i)==preferred),None)
        if match is None: match=next((i for i in range(1,self.preset.count()) if self.preset.itemData(i)==self.settings),0)
        self.preset.setCurrentIndex(match)
        for key,button in self.color_buttons.items():button.setText(self.settings[key].upper());button.setIcon(swatch(self.settings[key]))
        for key,slider in self.sliders.items():slider.setValue(self.settings[key]);self.update_value(key)
        self.density.setCurrentIndex(self.density.findData(self.settings['density']))
        self.updating=False

    def update_value(self,key):
        value=self.settings[key]
        self.values[key].setText(f'{value:+d}%' if key=='brightness' else f'{value} px' if key=='corners' else f'{value}%')

    def change(self,key,value):
        if self.updating:return
        self.settings[key]=value
        if key in self.values:self.update_value(key)
        self.preset.blockSignals(True);self.preset.setCurrentIndex(0);self.preset.blockSignals(False)
        self.preview_timer.start()

    def preview(self):self.host.apply_appearance(self.settings)

    def choose_preset(self):
        if self.updating:return
        values=self.preset.currentData()
        if values:
            name=self.preset.currentText();self.settings=normalize(values);self.sync(name);self.preview_timer.start()

    def pick_color(self,key):
        # Color dialog itself is a reversible live preview too.
        previous=dict(self.settings)
        dialog=QColorDialog(QColor(self.settings[key]),self);dialog.setWindowTitle('Choose '+key+' color')
        dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog)
        def changed(value):
            self.change(key,value.name());self.color_buttons[key].setText(value.name().upper());self.color_buttons[key].setIcon(swatch(value.name()))
        dialog.currentColorChanged.connect(changed)
        if dialog.exec()!=QDialog.DialogCode.Accepted:
            self.settings=previous;self.sync();self.preview_timer.start()

    def add_preset(self):
        name,ok=QInputDialog.getText(self,'Save appearance preset','Preset name:')
        name=name.strip()[:40]
        if not ok or not name:return
        if name in PRESETS:
            QMessageBox.information(self,'Choose another name','Built-in presets keep their original colors. Give yours a new name.');return
        existing=next((p for p in self.custom if p['name']==name),None)
        if existing and QMessageBox.question(self,'Replace preset',f'Replace “{name}” with this look?')!=QMessageBox.StandardButton.Yes:return
        if not existing and len(self.custom)>=20:
            QMessageBox.information(self,'Preset limit','You can save 20 custom presets. Use an existing name to replace one.');return
        self.custom=[p for p in self.custom if p['name']!=name]+[dict(name=name,settings=dict(self.settings))]
        self.sync(name)

    def reset(self):
        self.settings=dict(DEFAULT);self.sync();self.preview_timer.start()

    def accept(self):
        self.preview_timer.stop();self.preview()
        document=normalize_document(dict(settings=self.settings,presets=self.custom))
        try:save_preferences(self.host.appearance_path,document)
        except OSError as exc:
            QMessageBox.warning(self,'Could not save appearance',str(exc));return
        self.host.appearance_document=document;self.saved=True;super().accept()

    def finish(self,*_):
        self.preview_timer.stop()
        if not self.saved:self.host.apply_appearance(self.original['settings'])
