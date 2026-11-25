"""Single-screen sequential YouChoose classroom demonstration."""
from __future__ import annotations
import sys
from PIL import Image
from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QFont
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSpinBox, QFrame, QProgressBar, QScrollArea, QSizePolicy, QFileDialog)
from .engine import SequentialDemo, normalize_image, sample_image, hash_challenge

STYLE = """
QWidget { background: #f4f6f8; color: #182638; font-family: 'Segoe UI', Arial; font-size: 14px; }
QFrame#panel { background: white; border: 1px solid #dce3e9; border-radius: 12px; }
QFrame#panel QLabel { background: transparent; }
QWidget#imageView { background: transparent; }
QLabel#muted { color: #586b7d; }
QPushButton { background: white; color: #20394c; border: 1px solid #b7c7d3; border-radius: 7px; padding: 9px 14px; font-weight: 600; }
QPushButton:hover { background: #e9f3f7; }
QPushButton:disabled { background: #edf0f3; color: #8796a5; border-color: #dce3e9; }
QPushButton#primary { background: #087d73; color: white; border-color: #087d73; }
QPushButton#primary:hover { background: #08675f; }
QPushButton#primary:disabled { background: #dbe8e5; color: #758d89; border-color: #dbe8e5; }
QSpinBox { background: white; border: 1px solid #b7c7d3; border-radius: 6px; padding: 5px; min-width: 68px; }
QProgressBar { background: #e5ecef; border: none; border-radius: 4px; height: 8px; text-align: center; }
QProgressBar::chunk { background: #087d73; border-radius: 4px; }
QScrollArea { border: 0; }
"""


def label(text='', size=14, bold=False, muted=False):
    w = QLabel(text); w.setWordWrap(True)
    f = QFont(); f.setPointSize(size); f.setBold(bold); w.setFont(f)
    if muted: w.setObjectName('muted')
    return w


def button(text, action, primary=False):
    b = QPushButton(text); b.clicked.connect(action)
    if primary: b.setObjectName('primary')
    return b


def panel():
    p = QFrame(); p.setObjectName('panel'); l = QVBoxLayout(p)
    l.setContentsMargins(13, 11, 13, 11); l.setSpacing(6)
    return p, l


class ImageView(QWidget):
    """Display image plus exact stripe boundaries; highlight current record."""
    def __init__(self, height=155):
        super().__init__(); self.setObjectName("imageView"); self.image = None; self.bounds = []; self.active = None
        self.setMinimumHeight(height); self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def sizeHint(self):
        return QSize(300, self.minimumHeight())

    def show_image(self, image, bounds=(), active=None):
        self.image = image; self.bounds = bounds; self.active = active; self.update()

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self.image is None:
            p.setPen(QColor('#8291a0')); p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'Generated when you start'); return
        im = self.image.convert('RGB')
        data = im.tobytes()
        q = QImage(data, im.width, im.height, im.width*3, QImage.Format.Format_RGB888)
        scale = min((self.width()-6)/im.width, (self.height()-6)/im.height)
        w,h = im.width*scale, im.height*scale
        x,y = (self.width()-w)/2, (self.height()-h)/2
        rect = QRectF(x,y,w,h); p.drawImage(rect,q)
        p.setPen(QPen(QColor(255,255,255,120), 0.7))
        for y0,_ in self.bounds[1:]:
            p.drawLine(QRectF(x,y+y0*scale,w,0).topLeft(), QRectF(x,y+y0*scale,w,0).topRight())
        if self.active is not None and self.active < len(self.bounds):
            y0,y1 = self.bounds[self.active]
            p.setPen(QPen(QColor('#ffcc45'), 2)); p.drawRect(QRectF(x+1,y+y0*scale,w-2,max(1,(y1-y0)*scale)))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle('YouChoose — Interactive protocol'); self.resize(1080, 800)
        self.source = sample_image(); self.demo = None
        scroll = QScrollArea(); scroll.setWidgetResizable(True); self.setCentralWidget(scroll)
        base = QWidget(); scroll.setWidget(base); root = QVBoxLayout(base)
        root.setContentsMargins(22, 16, 22, 16); root.setSpacing(10)
        root.addWidget(label('YouChoose', 26, True))
        root.addWidget(label('Select one record at a time, then recover the secret challenge from the received image.', 11, muted=True))
        controls = QHBoxLayout(); controls.addWidget(label('TLS records', 12, True))
        self.count = QSpinBox(); self.count.setRange(2,80); self.count.setValue(10); controls.addWidget(self.count)
        self.load_btn = button('Change image', self.load_image); controls.addWidget(self.load_btn)
        self.start_btn = button('Start protocol', self.start, True); controls.addWidget(self.start_btn)
        self.reset_btn = button('Reset', self.reset); controls.addWidget(self.reset_btn); controls.addStretch()
        root.addLayout(controls)
        # All three views share the same stripe coordinates.
        imgs = QHBoxLayout(); imgs.setSpacing(10); self.views=[]; self.tokens=[]; self.choices=[]
        for i,title in enumerate(('Original image (m)', 'Message 0 (m₀)', 'Message 1 (m₁)')):
            frame,l = panel(); l.addWidget(label(title,12,True)); view=ImageView(155); l.addWidget(view,1); self.views.append(view)
            if i == 0:
                l.addWidget(label('Default image • raw RGB demo',10,muted=True)); l.addWidget(label('Prover P generates both variants.',10,muted=True))
            else:
                t=label('Record —',10,muted=True); l.addWidget(t); self.tokens.append(t)
                b=button(f'Forward block {i-1}', lambda checked=False, bit=i-1:self.forward(bit), True); l.addWidget(b); self.choices.append(b)
            imgs.addWidget(frame,1)
        root.addLayout(imgs, 1)
        self.status = label('', 14, True); root.addWidget(self.status)
        self.progress=QProgressBar(); self.progress.setTextVisible(False); root.addWidget(self.progress)
        # Live message at bottom; recovery displayed alongside it.
        bottom=QHBoxLayout(); bottom.setSpacing(10)
        frame,l=panel(); l.addWidget(label('Message forming at server S', 13, True)); self.output=ImageView(170); l.addWidget(self.output,1)
        self.delivered_text=label('',10,muted=True); l.addWidget(self.delivered_text); bottom.addWidget(frame,1)
        frame,l=panel(); l.addWidget(label('Recover challenge at prover P',13,True))
        self.recovery_desc=label('After all records arrive, P retrieves the assembled image and compares its blocks with m₀ and m₁.',11,muted=True); l.addWidget(self.recovery_desc)
        self.d_label=label('Verifier d: —',11,True); l.addWidget(self.d_label)
        self.dp_label=label('Prover d′: —',11,True); l.addWidget(self.dp_label)
        self.recover_btn=button('Retrieve image & recover d′',self.recover,True); l.addWidget(self.recover_btn)
        self.verify_btn=button('Verify H(d′ || pkV)',self.verify); l.addWidget(self.verify_btn)
        self.result=label('',11,True); l.addWidget(self.result); l.addStretch(); bottom.addWidget(frame,1)
        root.addLayout(bottom,1)
        root.addWidget(label('Educational simulation: highlighted image stripes represent TLS records. The observer plays verifier V; displayed plaintext is for teaching only. No real TLS, OT, or account access.',9,muted=True))
        self.reset()

    def load_image(self):
        path,_=QFileDialog.getOpenFileName(self,'Choose image','','Images (*.png *.jpg *.jpeg *.bmp *.webp)')
        if path:
            try:
                with Image.open(path) as im: self.source=im.convert('RGB')
            except Exception as exc:
                self.status.setText(f'Could not open image: {exc}'); return
            self.reset()

    def reset(self):
        self.demo=None; self.count.setEnabled(True); self.load_btn.setEnabled(True); self.start_btn.setEnabled(True)
        self.views[0].show_image(normalize_image(self.source))
        for v in self.views[1:]: v.show_image(None)
        self.output.show_image(None); self.status.setText('Ready — choose a record count and start the protocol.')
        self.progress.setRange(0,self.count.value()); self.progress.setValue(0)
        self.delivered_text.setText('No records forwarded yet.'); self.d_label.setText('Verifier d: —'); self.dp_label.setText('Prover d′: —')
        self.recovery_desc.setText('After all records arrive, P retrieves the assembled image and compares its blocks with m₀ and m₁.')
        self.result.clear(); self.recover_btn.setEnabled(False); self.verify_btn.setEnabled(False)
        for b,t in zip(self.choices,self.tokens): b.setEnabled(False); t.setText('Record —')

    def start(self):
        self.demo=SequentialDemo(self.source,self.count.value()); self.count.setEnabled(False); self.load_btn.setEnabled(False); self.start_btn.setEnabled(False)
        self.refresh()

    def forward(self, bit):
        if self.demo is None or self.demo.complete: return
        self.demo.forward(bit); self.refresh()

    def refresh(self):
        d=self.demo; s=d.sim; i=d.round_index; n=s.n_bits; active=None if d.complete else i
        for view,im in zip(self.views,(s.original,s.variant_0,s.variant_1)): view.show_image(im,s.boundaries,active)
        self.output.show_image(d.image,s.boundaries)
        self.progress.setRange(0,n); self.progress.setValue(i)
        self.delivered_text.setText(f'{i} of {n} records received. Grey area = not yet received.' if not d.complete else f'All {n} records received. Image ready to retrieve.')
        self.d_label.setText('Verifier d: '+self.bits(d.selections)+('  …' if not d.complete else ''))
        self.status.setText(f'Round {i+1} / {n} — V chooses one block to forward to S.' if not d.complete else 'Transmission complete — P can now retrieve the image.')
        for j,(b,t) in enumerate(zip(self.choices,self.tokens)):
            b.setEnabled(not d.complete)
            b.setText(f'Forward block {j}')
            t.setText('All records sent' if d.complete else f'Record {i+1}  •  ID {(s.records[i].token_0,s.records[i].token_1)[j][:10]}')
        self.recover_btn.setEnabled(d.complete and d.recovered is None)

    @staticmethod
    def bits(bits):
        if not bits: return '—'
        return ' '.join(''.join(str(b) for b in bits[i:i+10]) for i in range(0,len(bits),10))

    def recover(self):
        d=self.demo; bits=d.recover()
        self.dp_label.setText('Prover d′: '+self.bits(bits))
        self.recovery_desc.setText('P compares each retrieved block with its two originals. A match with m₀ yields 0; a match with m₁ yields 1. Recovered from image bytes, not V’s choice list.')
        self.recover_btn.setEnabled(False); self.verify_btn.setEnabled(True)
        self.result.setText(f'All {len(bits)} block matches recovered.')

    def verify(self):
        d=self.demo; ok=d.verify(); self.result.setText(('✓ Accepted: hashes match' if ok else 'Rejected: hashes differ') + '\n'+f'H(d′ || pkV) = {hash_challenge(d.recovered)[:16]}…')
        self.verify_btn.setEnabled(False)


def launch():
    app=QApplication.instance() or QApplication(sys.argv); app.setStyleSheet(STYLE)
    window=MainWindow(); window.show(); return app.exec()
