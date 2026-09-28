"""Portable subtitle projects and text formats, independent of Qt or ML runtimes."""
from __future__ import annotations
import copy
import html
import json
import math
import re
from pathlib import Path
from uuid import uuid4

DEFAULT_STYLE = dict(font='Trebuchet MS', size=38, color='#FF829E', outline=2,
                     outline_color='#302039', margin=42)


def new_document(video='', language='auto'):
    return dict(schema=1, video=str(video), language=language, target_language='en',
                cues=[], style=dict(DEFAULT_STYLE), context='')


def cue(start, end, text='', translation=''):
    return dict(id=uuid4().hex, start=round(float(start), 3), end=round(float(end), 3),
                source=str(text), translation=str(translation), suggestion='')


def validate_document(doc):
    if not isinstance(doc, dict) or doc.get('schema') != 1 or not isinstance(doc.get('cues'), list):
        raise ValueError('This is not a supported JuicyCensor subtitle project.')
    ids = set()
    for item in doc['cues']:
        if not isinstance(item, dict) or not {'start','end','source','id'} <= item.keys():
            raise ValueError('A subtitle entry is missing its text, ID, or timing.')
        a, b = float(item['start']), float(item['end'])
        if not math.isfinite(a + b) or not 0 <= a < b <= 360000:
            raise ValueError('Every subtitle needs an end time after its start, within 100 hours.')
        if not isinstance(item.get('id'), str) or item['id'] in ids:
            raise ValueError('Subtitle identifiers must be unique.')
        ids.add(item['id'])
        for name in ('source', 'translation', 'suggestion'):
            if not isinstance(item.get(name, ''), str):
                raise ValueError('Subtitle text must be a string.')
    style = doc.get('style', DEFAULT_STYLE)
    if not isinstance(style, dict): raise ValueError('Invalid subtitle style.')
    for field, minimum, maximum in [('size',12,100),('outline',0,8),('margin',0,250)]:
        value=style.get(field, DEFAULT_STYLE[field])
        if not isinstance(value,(int,float)) or not math.isfinite(value) or not minimum<=value<=maximum:
            raise ValueError('Invalid subtitle style: '+field)
    for field in ('color','outline_color'):
        if not re.fullmatch(r'#[0-9A-Fa-f]{6}',str(style.get(field,DEFAULT_STYLE[field]))):
            raise ValueError('Invalid subtitle color.')
    if not isinstance(style.get('font',DEFAULT_STYLE['font']),str): raise ValueError('Invalid subtitle font.')
    return doc


def save_project(path, doc):
    validate_document(doc)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    try:
        temp.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def load_project(path):
    doc = validate_document(json.loads(Path(path).read_text(encoding='utf-8-sig')))
    doc['style'] = dict(DEFAULT_STYLE, **doc.get('style', {}))
    return doc


def timestamp(value, ass=False, vtt=False):
    units = 100 if ass else 1000
    ticks = round(float(value) * units)
    hours, ticks = divmod(ticks, 3600 * units)
    minutes, ticks = divmod(ticks, 60 * units)
    seconds, fraction = divmod(ticks, units)
    return f'{hours:01d}:{minutes:02d}:{seconds:02d}.{fraction:02d}' if ass else \
        f'{hours:02d}:{minutes:02d}:{seconds:02d}{"." if vtt else ","}{fraction:03d}'


def parse_time(value):
    parts = value.strip().replace(',', '.').split(':')
    if len(parts) not in (2, 3):
        raise ValueError('Invalid subtitle timestamp.')
    seconds = float(parts[-1])
    minutes = int(parts[-2])
    hours = int(parts[0]) if len(parts) == 3 else 0
    if not (0 <= seconds < 60 and 0 <= minutes < 60 and hours >= 0):
        raise ValueError('Invalid subtitle timestamp.')
    return hours * 3600 + minutes * 60 + seconds


def import_subtitles(path):
    path = Path(path)
    content = path.read_text(encoding='utf-8-sig').replace('\r\n', '\n').replace('\r', '\n')
    doc = new_document()
    if path.suffix.lower() in ('.ass', '.ssa'):
        fields = []
        section = ''
        for line in content.splitlines():
            if line.startswith('['): section = line.strip().lower()
            elif section == '[events]' and line.startswith('Format:'):
                fields = [x.strip().lower() for x in line[7:].split(',')]
            elif section == '[events]' and line.startswith('Dialogue:'):
                if not fields or fields[-1] != 'text':
                    raise ValueError('ASS event format is unsupported.')
                values = dict(zip(fields, line[9:].lstrip().split(',', len(fields)-1)))
                text = re.sub(r'\{[^}]*\}', '', values['text']).replace('\\N', '\n').replace('\\n', '\n').replace('\\h', ' ')
                doc['cues'].append(cue(parse_time(values['start']), parse_time(values['end']), text))
        # Import text/timing explicitly; complex ASS animation/layout is not a project style.
        doc['import_note'] = 'ASS text and timings imported. Set appearance in the Style tab; imported effects are not retained.'
    else:
        for block in re.split(r'\n\s*\n', content.strip()):
            lines = block.splitlines()
            index = next((i for i, line in enumerate(lines) if '-->' in line), None)
            if index is None: continue
            start, end = lines[index].split('-->', 1)
            text = html.unescape(re.sub(r'<[^>]+>', '', '\n'.join(lines[index+1:])))
            doc['cues'].append(cue(parse_time(start), parse_time(end.strip().split()[0]), text))
    if not doc['cues']:
        raise ValueError('No subtitle entries were found. Use UTF-8 SRT, VTT, or ASS.')
    doc['cues'].sort(key=lambda item: item['start'])
    return validate_document(doc)


def track_text(item, track):
    # Never silently substitute untranslated source into a target-language track.
    return item.get('translation' if track == 'translation' else 'source', '')


def ass_color(rgb):
    if not re.fullmatch(r'#[0-9A-Fa-f]{6}', rgb):
        raise ValueError('Choose a valid subtitle color.')
    return '&H00' + rgb[5:7] + rgb[3:5] + rgb[1:3]


def export_text(doc, format_name, track='source'):
    validate_document(doc)
    if not doc['cues']: raise ValueError('There are no subtitles to export.')
    if track == 'translation' and any(not c.get('translation', '').strip() for c in doc['cues']):
        raise ValueError('Some translations are empty. Fill them in or export the source track.')
    rows = sorted(doc['cues'], key=lambda c: c['start'])
    if format_name == 'ass':
        style = dict(DEFAULT_STYLE, **doc.get('style', {}))
        font = str(style['font']).replace(',', '').replace('\n', '').replace('\r', '')
        size = max(12, min(100, int(style['size'])))
        outline = max(0, min(8, float(style['outline'])))
        margin = max(0, min(250, int(style['margin'])))
        text = ('[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n'
                'WrapStyle: 0\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\n'
                'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n')
        text += f'Style: Default,{font},{size},{ass_color(style["color"])},{ass_color(style["color"])},{ass_color(style["outline_color"])},&H80000000,-1,0,0,0,100,100,0,0,1,{outline},0.7,2,64,64,{margin},1\n\n[Events]\n'
        text += 'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'
        for row in rows:
            value = track_text(row, track).replace('\\', '＼').replace('{', '｛').replace('}', '｝').replace('\r', '').replace('\n', '\\N')
            text += f'Dialogue: 0,{timestamp(row["start"], True)},{timestamp(row["end"], True)},Default,,0,0,0,,{value}\n'
        return text
    if format_name not in ('srt', 'vtt'):
        raise ValueError('Unsupported subtitle export format.')
    vtt = format_name == 'vtt'
    result = 'WEBVTT\n\n' if vtt else ''
    for index, row in enumerate(rows, 1):
        value = html.escape(track_text(row, track), quote=False)
        result += f'{index}\n{timestamp(row["start"], vtt=vtt)} --> {timestamp(row["end"], vtt=vtt)}\n{value}\n\n'
    return result


def quality_notes(item, previous=None):
    value = item.get('translation') or item['source']
    duration = item['end'] - item['start']
    notes = []
    if len(value.replace('\n', '')) / duration > 22: notes.append('Fast reading')
    if any(len(line) > 48 for line in value.splitlines()): notes.append('Long line')
    if previous and item['start'] < previous['end'] - .001: notes.append('Overlap')
    if item.get('suggestion'): notes.append('Suggestion')
    return ' · '.join(notes)


class History:
    def __init__(self): self.undo_items, self.redo_items = [], []
    def record(self, doc):
        self.undo_items.append(copy.deepcopy(doc))
        self.undo_items = self.undo_items[-100:]
        self.redo_items.clear()
    def undo(self, doc):
        if not self.undo_items: return doc
        self.redo_items.append(copy.deepcopy(doc))
        return self.undo_items.pop()
    def redo(self, doc):
        if not self.redo_items: return doc
        self.undo_items.append(copy.deepcopy(doc))
        return self.redo_items.pop()
