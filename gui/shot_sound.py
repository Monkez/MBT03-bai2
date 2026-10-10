import os

from PyQt5.QtCore import QObject, QUrl
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer

import config as cf


class ShotSound(QObject):
    """Preload independent channels so bursts do not block the Qt event loop."""

    def __init__(self, parent=None):
        super().__init__(parent)
        source = QMediaContent(QUrl.fromLocalFile(
            os.path.join(cf.DATA_DIR, "assets", "sounds", "TN.mp3")
        ))
        self._players = []
        self._next_channel = 0
        self._reported_error = False
        for _ in range(8):
            player = QMediaPlayer(self, QMediaPlayer.LowLatency)
            player.error.connect(lambda _error, p=player: self._report_error(p))
            player.setMedia(source)
            self._players.append(player)

    def _report_error(self, player):
        if not self._reported_error:
            print(f"[Audio] Khong phat duoc tieng no: {player.errorString()!a}")
            self._reported_error = True

    def play(self):
        player = self._players[self._next_channel]
        self._next_channel = (self._next_channel + 1) % len(self._players)
        player.stop()
        player.play()

    def stop(self):
        for player in self._players:
            player.stop()
