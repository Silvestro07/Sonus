from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import theme
from .. import voice_sync
from ..together_sync import nowMs

FLASH_MS = 140


def phaseAt(sync, now):
    """(index, phase) running at `now`, the next one during a pause, or (None, None) when all are over."""
    beatMs = sync["beatMs"]
    for index, phase in enumerate(sync["phases"]):
        if now < phase["beats"][-1] + beatMs:
            return index, phase
    return None, None


def instructionFor(sync, phase, now):
    name = sync.get("partnerName") or "il tuo amico"
    if phase is None:
        return "Calcolo..."
    first = phase["beats"][0]
    waiting = now < first - 150
    role = phase["role"]
    if role == "click":
        text = "Prova: tocca il cerchio (o premi Spazio) INSIEME ai click che senti"
    elif role == "sing":
        text = f"Tocca a te: di' «TA» nel microfono a ogni click. {name} tocca a tempo con la tua voce"
    else:
        text = f"Tocca a {name}: ascolta la sua voce e tocca il cerchio a ritmo con i suoi «TA»"
    if waiting:
        seconds = max(1, int((first - now + 999) // 1000))
        return f"Tra {seconds}...  {text}"
    return text


class BeatLight(QWidget):
    """Big round button: it lights up on every beat of my clicks and registers taps."""

    def __init__(self, onTap, parent=None):
        super().__init__(parent)
        self.onTap = onTap
        self.level = 0.0
        self.enabled = True
        self.tappedAt = 0
        self.setMinimumSize(180, 180)
        self.setCursor(Qt.PointingHandCursor)

    def setLevel(self, level, enabled):
        if abs(level - self.level) > 0.01 or enabled != self.enabled:
            self.level = level
            self.enabled = enabled
            self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.tap()

    def tap(self):
        if not self.enabled:
            return
        self.tappedAt = nowMs()
        self.onTap(self.tappedAt)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        side = min(self.width(), self.height()) - 8
        rect = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        base = QColor(theme.ELEVATED if hasattr(theme, "ELEVATED") else "#282828")
        accent = QColor(theme.ACCENT)
        color = QColor(
            int(base.red() + (accent.red() - base.red()) * self.level),
            int(base.green() + (accent.green() - base.green()) * self.level),
            int(base.blue() + (accent.blue() - base.blue()) * self.level))
        if not self.enabled:
            color.setAlpha(120)
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(rect)
        if nowMs() - self.tappedAt < 120:
            painter.setBrush(QColor(255, 255, 255, 70))
            painter.drawEllipse(rect.adjusted(side * 0.08, side * 0.08, -side * 0.08, -side * 0.08))
        painter.setPen(QColor(theme.TEXT if self.level < 0.5 else theme.ACCENT_TEXT))
        font = painter.font()
        font.setPixelSize(int(side * 0.14))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignCenter, "TOCCA" if self.enabled else "TA!")


class VoiceSyncDialog(QDialog):
    """Guides the two people through "Sincronizza voci" (method in app/voice_sync.py)."""

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("Sincronizza voci")
        self.setModal(False)
        self.setMinimumWidth(460)
        self.sync = controller.voiceSync
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        self.titleLabel = QLabel("")
        self.titleLabel.setObjectName("h2")
        layout.addWidget(self.titleLabel)
        self.stepLabel = QLabel("")
        self.stepLabel.setObjectName("sub")
        layout.addWidget(self.stepLabel)
        self.instructionLabel = QLabel("")
        self.instructionLabel.setWordWrap(True)
        self.instructionLabel.setMinimumHeight(48)
        layout.addWidget(self.instructionLabel)
        self.light = BeatLight(self.controller.voiceSyncTap)
        layout.addWidget(self.light, 1)
        self.resultLabel = QLabel("")
        self.resultLabel.setWordWrap(True)
        self.resultLabel.hide()
        layout.addWidget(self.resultLabel)
        self.choiceButtons = []
        choices = QVBoxLayout()
        for mode in (voice_sync.MODE_ME, voice_sync.MODE_THEM, voice_sync.MODE_HALF):
            button = QPushButton("")
            button.clicked.connect(lambda checked=False, mode=mode: self._choose(mode))
            button.hide()
            choices.addWidget(button)
            self.choiceButtons.append((mode, button))
        layout.addLayout(choices)
        buttons = QHBoxLayout()
        self.retryButton = QPushButton("Riprova")
        self.retryButton.clicked.connect(self._retry)
        self.retryButton.hide()
        buttons.addWidget(self.retryButton)
        buttons.addStretch()
        self.closeButton = QPushButton("Annulla")
        self.closeButton.clicked.connect(self.close)
        buttons.addWidget(self.closeButton)
        layout.addLayout(buttons)
        hint = QLabel("Usate le cuffie se potete. Toccate a RITMO, non appena sentite il suono: "
                      "così il tempo di reazione non conta.")
        hint.setObjectName("small")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)
        self.timer.start()
        controller.voiceSyncChanged.connect(self._onChanged)
        self._onChanged(controller.voiceSync)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self.light.tap()
            return
        super().keyPressEvent(event)

    def _onChanged(self, sync):
        self.sync = sync
        if sync is None:
            self.titleLabel.setText("Sincronizzazione annullata")
            self.instructionLabel.setText("")
            self.light.setLevel(0.0, False)
            self.closeButton.setText("Chiudi")
            for _, button in self.choiceButtons:
                button.hide()
            return
        name = sync.get("partnerName") or "il tuo amico"
        self.titleLabel.setText(f"Sincronizza voci con {name}")
        status = sync["status"]
        self.retryButton.setVisible(status == "failed")
        self.resultLabel.setVisible(status in ("waiting", "done", "applied", "failed"))
        self.closeButton.setText("Annulla" if status in ("running", "waiting", "done") else "Chiudi")
        if status == "failed":
            self.resultLabel.setText(f"Misura non riuscita. {sync.get('error') or ''}")
        elif status == "waiting":
            self.resultLabel.setText(f"Fatto! Aspetto il risultato di {name}...")
        elif status == "done":
            mine, theirs = sync["myNeed"], sync["theirNeed"]
            self.resultLabel.setText(
                f"Tu senti la voce di {name} {self._describe(mine)}. {name} sente la tua {self._describe(theirs)}.\n"
                "Una voce non può arrivare in anticipo: si può essere perfetti in una direzione sola. Scegli:")
            for mode, button in self.choiceButtons:
                late = voice_sync.mismatch(mode, mine, theirs)
                label = {voice_sync.MODE_ME: f"Io sento {name} a tempo",
                         voice_sync.MODE_THEM: f"{name} sente me a tempo",
                         voice_sync.MODE_HALF: "A metà (un po' di ritardo per entrambi)"}[mode]
                button.setText(f"{label}   ·   tu {self._short(late[0])}, {name} {self._short(late[1])}")
                button.show()
            self.choiceButtons[0][1].setObjectName("accent")
            self.choiceButtons[0][1].style().polish(self.choiceButtons[0][1])
        elif status == "applied":
            applied = sync.get("applied") or {}
            delay = applied.get("delay") or 0
            self.resultLabel.setText("Voci sincronizzate. Il tuo ritardo: " + (f"+{delay / 1000:.2f} s" if delay else "nessuno") +
                                     ". Da ora la stanza tiene le canzoni allineate al decimo di secondo.")
            for _, button in self.choiceButtons:
                button.hide()

    @staticmethod
    def _describe(needMs):
        if needMs is None:
            return "(?)"
        if abs(needMs) < 25:
            return "perfettamente a tempo"
        return f"{abs(needMs)} ms " + ("in ritardo" if needMs > 0 else "in anticipo")

    @staticmethod
    def _short(lateMs):
        return "a tempo" if abs(lateMs) < 25 else f"{lateMs:+d} ms"

    def _tick(self):
        sync = self.sync
        if not sync or sync["status"] != "running":
            self.light.setLevel(0.0, False)
            if sync and sync["status"] != "running":
                self.stepLabel.setText("")
                self.instructionLabel.setText("")
            return
        now = nowMs()
        index, phase = phaseAt(sync, now)
        if phase is None:
            self.light.setLevel(0.0, False)
            self.instructionLabel.setText("Calcolo...")
            return
        self.stepLabel.setText(f"Passo {index + 1} di {len(sync['phases'])}")
        self.instructionLabel.setText(instructionFor(sync, phase, now))
        level = 0.0
        if phase["role"] in ("click", "sing"):
            distance = min(abs(now - beat) for beat in phase["beats"])
            later = [now - beat for beat in phase["beats"] if now >= beat]
            if later and min(later) < FLASH_MS:
                level = 1.0 - min(later) / FLASH_MS
            elif distance < 40:
                level = 0.6
        self.light.setLevel(level, phase["role"] != "sing")

    def _choose(self, mode):
        self.controller.applyVoiceSync(mode)

    def _retry(self):
        sync = self.sync
        if sync:
            self.controller.startVoiceSync(sync["partner"])

    def closeEvent(self, event):
        if self.sync and self.sync["status"] in ("running", "waiting", "done"):
            self.controller.cancelVoiceSync(notifyPartner=True)
        self.timer.stop()
        super().closeEvent(event)
