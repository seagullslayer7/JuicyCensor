"""Small, consistent line icons for the native editor toolbars."""
from PySide6.QtCore import Qt, QSize, QPointF
from appearance import color as theme_color
from PySide6.QtGui import QIcon, QPixmap, QPainter, QPen, QColor, QPolygonF


def tool_icon(name, primary=False):
    pix = QPixmap(40,40); pix.fill(Qt.GlobalColor.transparent); pix.setDevicePixelRatio(2)
    p = QPainter(pix); p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(theme_color('on_accent' if primary else 'accent_text'),1.6,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
    def line(*v): p.drawLine(*v)
    if name in ('plus','add'):
        line(10,4,10,16); line(4,10,16,10)
    elif name in ('remove','trash'):
        line(4,5,16,5); line(8,3,12,3); p.drawRoundedRect(5,5,10,12,1,1); line(8,8,8,14); line(12,8,12,14)
    elif name in ('cancel','dismiss'):
        line(5,5,15,15); line(15,5,5,15)
    elif name in ('apply','accept'):
        line(4,10,8,14); line(8,14,16,5)
    elif name == 'split':
        p.drawEllipse(3,3,5,5); p.drawEllipse(3,12,5,5); line(7,7,16,15); line(7,13,16,5)
    elif name == 'merge':
        line(3,4,7,4); line(7,4,12,10); line(3,16,7,16); line(7,16,12,10); line(12,10,17,10); line(14,7,17,10); line(14,13,17,10)
    elif name in ('undo','redo'):
        if name == 'redo': p.translate(20,0); p.scale(-1,1)
        line(4,8,8,4); line(4,8,8,12); line(4,8,12,8); p.drawArc(9,8,7,8,-90*16,180*16)
    elif name == 'fit':
        for a,b,c,d in ((3,7,3,3),(3,3,7,3),(13,3,17,3),(17,3,17,7),(3,13,3,17),(3,17,7,17),(13,17,17,17),(17,13,17,17)): line(a,b,c,d)
    elif name in ('open','queue'):
        if name == 'open':
            p.drawPolyline(QPolygonF([QPointF(3,16),QPointF(3,4),QPointF(8,4),QPointF(10,6),QPointF(17,6),QPointF(17,16),QPointF(3,16)]))
        else:
            for y in (5,10,15): line(7,y,17,y); line(3,y,3,y)
    elif name == 'save':
        p.drawRoundedRect(3,3,14,14,1,1); p.drawRect(6,3,8,5); p.drawRect(6,12,8,5)
    elif name == 'export':
        line(4,12,4,17); line(4,17,16,17); line(16,17,16,12); line(10,13,10,3); line(6,7,10,3); line(14,7,10,3)
    elif name in ('play','preview'):
        p.drawPolygon(QPolygonF([QPointF(6,4),QPointF(16,10),QPointF(6,16)]))
    elif name == 'wave':
        for x,h in ((3,3),(6,6),(10,8),(14,5),(17,2)): line(x,10-h,x,10+h)
    elif name in ('transcribe','analyze'):
        p.drawRoundedRect(7,2,6,10,3,3); p.drawArc(4,6,12,9,180*16,180*16); line(10,15,10,18); line(7,18,13,18)
    elif name in ('translate','smart'):
        if name == 'smart':
            p.drawPolygon(QPolygonF([QPointF(10,2),QPointF(12,8),QPointF(18,10),QPointF(12,12),QPointF(10,18),QPointF(8,12),QPointF(2,10),QPointF(8,8)]))
        else:
            line(3,5,16,5); line(13,2,16,5); line(13,8,16,5); line(17,15,4,15); line(7,12,4,15); line(7,18,4,15)
    elif name == 'notes':
        p.drawRoundedRect(4,2,12,16,1,1)
        for y in (6,10,14): line(7,y,13,y)
    p.end(); return QIcon(pix)


def decorate(button, name, primary=False):
    button.setProperty('themeIcon',name); button.setProperty('themeIconPrimary',primary)
    button.setIcon(tool_icon(name,primary)); button.setIconSize(QSize(18,18))
    if not button.accessibleName(): button.setAccessibleName(button.toolTip() or button.text())
    return button


def decorate_text(button, text, primary=False):
    label = text.lower().lstrip('+ ').strip()
    choices = [('add video','open'),('video queue','queue'),('open subtitle','open'),('save','save'),
        ('analyze','analyze'),('transcribe','transcribe'),('audio →','translate'),('smart translate','smart'),
        ('export','export'),('view last','open'),('play line','preview'),('preview region','preview'),
        ('line','plus'),('split','split'),('merge','merge'),('remove','trash'),('fit','fit'),
        ('apply','apply'),('accept','accept'),('dismiss','dismiss'),('cancel','cancel'),
        ('undo','undo'),('redo','redo'),('scene notes','notes'),('set censor','split'),('end censor','apply')]
    for prefix,name in choices:
        if label.startswith(prefix): return decorate(button,name,primary)
    return button
