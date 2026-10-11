import os
from collections import deque

from PyQt5.QtCore import QObject, QTimer, QUrl
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer

import config as cf


class HitSound(QObject):
    """Read each target/pedestal pair once per exercise, without overlapping voices."""

    PLAYBACK_RATE = 1.75

    def __init__(self, parent=None):
        super().__init__(parent)
        self._announced = set()
        self._pending = deque()
        self._active = False
        self._enabled = True
        self._player = QMediaPlayer(self)
        self._player.mediaStatusChanged.connect(self._on_status)
        self._player.error.connect(self._on_error)

    def announce(self, port_id, class_id):
        key = (port_id, class_id)
        if not self._enabled or port_id not in (1, 2, 3, 4) or key in self._announced:
            return
        self._announced.add(key)
        self._pending.append(port_id)
        self._play_next()

    def _play_next(self):
        if self._active or not self._pending:
            return
        port_id = self._pending.popleft()
        self._active = True
        self._player.setMedia(QMediaContent(QUrl.fromLocalFile(
            os.path.join(cf.DATA_DIR, "assets", "sounds", "noti", f"{port_id}.mp3")
        )))
        if not self._active:
            return
        self._player.setPlaybackRate(self.PLAYBACK_RATE)
        self._player.play()

    def _on_status(self, status):
        if status == QMediaPlayer.EndOfMedia:
            self._finish_current()

    def _on_error(self, error):
        if error != QMediaPlayer.NoError:
            print(f"[Audio] Khong doc duoc so be: {self._player.errorString()!a}")
            self._finish_current()

    def _finish_current(self):
        if not self._active:
            return
        self._active = False
        self._player.stop()
        QTimer.singleShot(0, self._play_next)

    def stop(self):
        self._enabled = False
        self._pending.clear()
        self._active = False
        self._player.stop()

    def reset(self):
        self.stop()
        self._announced.clear()
        self._enabled = True
