"""Audio ruler with selectable, trimmable timing blocks shared by both editors."""
import math
from PySide6.QtCore import Qt, Signal, QRectF, QEvent
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget
from subtitle_document import timestamp
from appearance import color as theme_color


class Timeline(QWidget):
    seek = Signal(float)
    view_changed = Signal()
    region_selected = Signal(int)
    region_edited = Signal(int, float, float)

    def __init__(self):
        super().__init__()
        self.duration, self.position, self.events = 0, 0, []
        self.peaks, self.peak_rate, self.waveform_message = [], 100, ''
        self.gain, self.reference = 1., 1.
        self.draft_start = None
        self.zoom, self.offset = 1., 0.
        self.selected_index, self.editable, self.drag = -1, True, None
        self.setMinimumHeight(128); self.setMaximumHeight(156)
        self.setMouseTracking(True); self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip('Drag either edge to trim; drag inside a block to move it. Click the ruler to seek. Scroll to zoom; Shift+scroll to pan. Esc cancels a drag.')

    @property
    def span(self): return self.duration/self.zoom if self.duration else 0
    def set_view(self, zoom, offset):
        self.zoom = max(1., min(zoom, max(1., self.duration*2)))
        self.offset = max(0., min(offset, self.duration-self.span))
        self.update(); self.view_changed.emit()
    def zoom_by(self, factor, fraction=None):
        if not self.duration: return
        if fraction is None: fraction = max(0., min(1., (self.position-self.offset)/self.span))
        anchor = self.offset+fraction*self.span
        zoom = max(1., min(self.zoom*factor, max(1., self.duration*2)))
        self.set_view(zoom, anchor-fraction*self.duration/zoom)
    def pan(self, value): self.set_view(self.zoom, value/10000*(self.duration-self.span))
    def follow(self, position):
        self.position = position
        if not self.drag and self.span and not self.offset <= position <= self.offset+self.span:
            self.set_view(self.zoom, position-self.span/2)
        self.update()
    def fraction_at(self, x): return max(0., min(1., (x-12)/max(1, self.width()-24)))
    def time_at(self, x): return self.offset+self.fraction_at(x)*self.span
    def x_at(self, seconds): return 12+(seconds-self.offset)/max(.001, self.span)*(self.width()-24)
    def set_waveform(self, data):
        self.peaks, self.peak_rate = data['peaks'], data.get('rate', 100)
        self.reference = max(max(self.peaks, default=0), .001)
        self.waveform_message = '' if self.peaks else 'No audio track available.'
        if not self.duration: self.duration = data['duration']
        self.update(); self.view_changed.emit()
    def set_gain(self, value): self.gain = value/100; self.update()
    def bounds(self, index):
        if self.drag and self.drag['index'] == index: return self.drag['preview']
        item = self.events[index]; return item['start'], item['end']
    def hit(self, pos):
        if not self.span or not 6 <= pos.y() < self.height()-24: return None
        candidates = []
        for index in range(len(self.events)):
            start, end = self.bounds(index); a, b = self.x_at(start), self.x_at(end)
            if a-6 <= pos.x() <= b+6:
                edge = min((abs(pos.x()-a), 'start'), (abs(pos.x()-b), 'end'))
                mode = edge[1] if edge[0] <= 7 else 'move'
                candidates.append((0 if mode != 'move' else 1, 0 if index == self.selected_index else 1, edge[0], index, mode))
        if not candidates: return None
        hit = min(candidates); return hit[3], hit[4]
    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), theme_color('canvas'))
        width, bottom = max(1, self.width()-24), self.height()-24
        center, amplitude = (bottom+26)/2, max(8, (bottom-44)/2)
        p.setPen(QPen(theme_color('border'), 1)); p.drawLine(12, round(center), self.width()-12, round(center))
        if self.span:
            p.save(); p.setClipRect(12, 4, width, bottom-4)
            order = [i for i in range(len(self.events)) if i != self.selected_index]
            if 0 <= self.selected_index < len(self.events): order.append(self.selected_index)
            for i in order:
                a, b = self.bounds(i)
                if b < self.offset or a > self.offset+self.span: continue
                rect = QRectF(self.x_at(a), 5, max(2, self.x_at(b)-self.x_at(a)), bottom-7)
                selected = i == self.selected_index
                p.fillRect(rect, theme_color('selected_block' if selected else 'block'))
            p.setPen(QPen(theme_color('wave'), 1))
            for x in range(width):
                first = max(0, int((self.offset+x/width*self.span)*self.peak_rate))
                last = max(first+1, math.ceil((self.offset+(x+1)/width*self.span)*self.peak_rate))
                peak = max(self.peaks[first:last], default=0)
                height = min(1., (peak/self.reference)**.65*self.gain)*amplitude
                p.drawLine(x+12, round(center-height), x+12, round(center+height))
            for i in order:
                a, b = self.bounds(i)
                if b < self.offset or a > self.offset+self.span: continue
                left, right = max(12., self.x_at(a)), min(self.width()-12., self.x_at(b))
                selected = i == self.selected_index
                p.setPen(QPen(theme_color('accent_text' if selected else 'wave_border'), 2 if selected else 1))
                for edge in (self.x_at(a), self.x_at(b)): p.drawLine(round(edge), 5, round(edge), bottom-3)
                text = self.events[i].get('source') or self.events[i].get('matched') or 'Subtitle'
                # Censor's source is metadata, not the visible match label.
                if 'matched' in self.events[i]: text = self.events[i]['matched']
                rect = QRectF(left+7, 7, max(0, right-left-14), 20)
                p.setPen(theme_color('on_selected_block' if selected else 'on_block'))
                p.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                           p.fontMetrics().elidedText(text.replace('\n', ' '), Qt.TextElideMode.ElideRight, int(rect.width())))
                if right-left > 86:
                    p.setPen(theme_color('on_selected_block' if selected else 'on_block'))
                    p.drawText(QRectF(left+7, bottom-22, right-left-14, 18), f'#{i+1}  ·  {b-a:.2f} s')
            if self.draft_start is not None:
                a,b = sorted((self.draft_start, self.position))
                draft = theme_color('wave'); draft.setAlpha(70)
                p.fillRect(QRectF(self.x_at(a), 5, self.x_at(b)-self.x_at(a), bottom-7), draft)
            p.restore()
            # A graduated ruler stays readable at every zoom level.
            target = self.span/max(1, width/105)
            magnitude = 10**math.floor(math.log10(max(.001, target)))
            step = next((v*magnitude for v in (1,2,5,10) if v*magnitude >= target), 10*magnitude)
            tick = math.ceil(self.offset/step)*step
            while tick <= self.offset+self.span:
                x = round(self.x_at(tick)); p.setPen(theme_color('border_hover')); p.drawLine(x, bottom, x, bottom+5)
                label = timestamp(tick).replace(',', '.')
                if step >= 1: label = label[:-4]
                p.setPen(theme_color('timeline_muted'))
                if x+4+p.fontMetrics().horizontalAdvance(label) <= self.width()-8:
                    p.drawText(x+4, self.height()-5, label)
                tick += step
            if self.offset <= self.position <= self.offset+self.span:
                x = round(self.x_at(self.position)); p.setPen(QPen(theme_color('playhead'), 2)); p.drawLine(x, 3, x, bottom)
        if self.waveform_message or not self.duration:
            p.setPen(theme_color('timeline_muted'))
            p.drawText(self.rect().adjusted(16, 28, -16, -26), Qt.AlignmentFlag.AlignCenter,
                       self.waveform_message or 'Open a video to see its audio waveform')
        p.end()
    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self.duration: return
        self.setFocus(); hit = self.hit(event.position())
        if hit:
            index, mode = hit
            self.region_selected.emit(index)
            if self.selected_index != index: return  # Editor rejected selection (e.g. invalid typed timing).
            if self.editable:
                a,b = self.bounds(index)
                self.drag = dict(index=index, mode=mode, anchor=self.time_at(event.position().x()),
                                 original=(a,b), preview=(a,b), x=event.position().x(), moved=False)
        else: self.seek.emit(self.time_at(event.position().x()))
        self.update()
    def mouseMoveEvent(self, event):
        if self.drag:
            d = self.drag
            if abs(event.position().x()-d['x']) < 3 and not d['moved']: return
            d['moved'] = True
            a,b = d['original']; delta = self.time_at(event.position().x())-d['anchor']
            minimum = min(.04, b-a)
            if d['mode'] == 'start': a = max(0., min(b-minimum, a+delta))
            elif d['mode'] == 'end': b = min(self.duration, max(a+minimum, b+delta))
            else:
                delta = max(-a, min(delta, self.duration-b)); a += delta; b += delta
            d['preview'] = (round(a,3), round(b,3))
            self.update(); return
        hit = self.hit(event.position())
        self.setCursor(Qt.CursorShape.SizeHorCursor if hit and hit[1] != 'move' and self.editable else
                       Qt.CursorShape.OpenHandCursor if hit and self.editable else Qt.CursorShape.PointingHandCursor)
    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self.drag: return
        d, self.drag = self.drag, None
        if d['moved'] and d['preview'] != d['original']: self.region_edited.emit(d['index'], *d['preview'])
        elif not d['moved']: self.seek.emit(self.time_at(event.position().x()))
        self.update()
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self.drag:
            self.drag = None; self.update(); event.accept()
        else: super().keyPressEvent(event)
    def event(self, event):
        if event.type() == QEvent.Type.ShortcutOverride and self.drag and event.key() == Qt.Key.Key_Escape:
            event.accept(); return True
        return super().event(event)
    def wheelEvent(self, event):
        if not self.duration or not event.angleDelta().y(): return
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.set_view(self.zoom, self.offset-self.span*.15*(1 if event.angleDelta().y()>0 else -1))
        else: self.zoom_by(1.5 if event.angleDelta().y()>0 else 1/1.5, self.fraction_at(event.position().x()))
        event.accept()
