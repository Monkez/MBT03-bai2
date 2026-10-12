import os
from collections import deque

from PyQt5.QtCore import QObject, QTimer, QUrl, pyqtSignal
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer

import config as cf


class ResultSound(QObject):
    """Play a pedestal name followed by its rank, on the Qt event loop."""

    changed = pyqtSignal()
    failed = pyqtSignal(str)
    RANK_FILES = {"Giỏi": "GIOI.mp3", "Khá": "KHA.mp3",
                  "Đạt": "DAT.mp3", "Không đạt": "KDAT.mp3"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.port_id = None
        self._pending = deque()
        self._playing = False
        self._player = QMediaPlayer(self)
        self._player.mediaStatusChanged.connect(self._on_status)
        self._player.error.connect(self._on_error)
        self._next_timer = QTimer(self)
        self._next_timer.setSingleShot(True)
        self._next_timer.timeout.connect(self._play_next)

    def start(self, port_id, rank):
        if self.port_id is not None or port_id not in (1, 2, 3, 4) or rank not in self.RANK_FILES:
            return
        self.port_id = port_id
        self._pending.extend((f"Beso{port_id}.mp3", self.RANK_FILES[rank]))
        self.changed.emit()
        self._play_next()

    def _play_next(self):
        if self.port_id is None or self._playing:
            return
        if not self._pending:
            self.stop()
            return
        filename = self._pending.popleft()
        path = os.path.join(cf.DATA_DIR, "assets", "sounds", filename)
        if not os.path.isfile(path):
            self._fail(f"Không tìm thấy âm thanh: {filename}")
            return
        self._playing = True
        self._player.setMedia(QMediaContent(QUrl.fromLocalFile(path)))
        if self._playing:
            self._player.setPlaybackRate(1.0)
            self._player.play()

    def _on_status(self, status):
        if status == QMediaPlayer.EndOfMedia and self._playing:
            self._playing = False
            self._player.stop()
            self._next_timer.start(0)

    def _on_error(self, error):
        if error != QMediaPlayer.NoError and self.port_id is not None:
            self._fail(f"Không phát được kết quả: {self._player.errorString()}")

    def _fail(self, message):
        self.stop()
        self.failed.emit(message)

    def stop(self):
        active = self.port_id is not None
        self.port_id = None
        self._next_timer.stop()
        self._pending.clear()
        self._playing = False
        self._player.stop()
        if active:
            self.changed.emit()
