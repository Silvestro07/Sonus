import json
import os
import time

import numpy

from app import audio_engine
from app.audio_engine import CHANNELS, PCM_CHUNK_FRAMES, SAMPLE_RATE, PcmStore


import pytest


@pytest.fixture
def application():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _frames(start, count):
    values = numpy.arange(start, start + count, dtype=numpy.int64) % 30000
    return numpy.repeat(values[:, None], CHANNELS, axis=1).astype(numpy.int16)


def test_pcmStoreReadsAcrossBlocksAndSpillsLongTracksToDisk():
    store = PcmStore(ramFrames=PCM_CHUNK_FRAMES * 2)
    total = PCM_CHUNK_FRAMES * 5 + 1234
    written = 0
    while written < total:
        count = min(7777, total - written)
        assert store.append(_frames(written, count))
        written += count
    assert len(store) == total
    # only 2 blocks + the one being filled stay in memory, the rest is in the temporary file
    assert store.memoryBytes() <= PCM_CHUNK_FRAMES * 3 * 2 * CHANNELS
    assert store.filePath and os.path.getsize(store.filePath) == PCM_CHUNK_FRAMES * 3 * 2 * CHANNELS
    for start in (0, PCM_CHUNK_FRAMES - 10, PCM_CHUNK_FRAMES * 2 - 5, PCM_CHUNK_FRAMES * 4 + 3, total - 100):
        assert numpy.array_equal(store.read(start, 100), _frames(start, 100))
    path = store.filePath
    store.close()
    assert not os.path.exists(path)
    assert not store.append(_frames(0, 10))


def test_engineFreesThePreviousSongWhenANewOneStarts(application):
    engine = audio_engine.AudioEngine()
    first = PcmStore()
    first.append(_frames(0, 1000))
    engine.generation = 3
    engine._attachBuffer(3, first)
    engine.decodedFrames = 1000
    engine.releaseAudio()
    assert first.closed and engine.buffer is None and engine.source().isEmpty()
    orphan = PcmStore()
    engine._attachBuffer(1, orphan)
    assert orphan.closed
    engine.shutdown()


def test_cuesAreMixedAtTheirTimeEvenWithoutMusic(application):
    engine = audio_engine.AudioEngine()
    engine.stream = None
    engine.setVolume(1.0)
    now = time.time()
    latency = engine.outputLatency()
    engine.cues = [(now + latency + 0.05, False)]
    block = numpy.zeros((SAMPLE_RATE // 5, CHANNELS), dtype=numpy.float32)
    engine._callback(block, len(block), None, None)
    loud = numpy.nonzero(numpy.abs(block[:, 0]) > 0.01)[0]
    assert len(loud)
    assert abs(loud[0] / SAMPLE_RATE - 0.05) < 0.01
    engine.shutdown()


def test_longPauseReleasesTheSongAndPlayResumesAtTheSamePoint(application, tmp_path):
    from app.player import Player
    player = Player()
    loads = []
    player._loadCurrent = lambda autoplay=True, startPosition=0: loads.append((autoplay, startPosition))
    player.queue = [{"id": 1, "path": str(tmp_path / "a.mp3"), "title": "A"}]
    player.currentIndex = 0
    engine = player.mediaPlayer
    store = PcmStore()
    store.append(_frames(0, SAMPLE_RATE * 2))
    engine._source = audio_engine.QUrl.fromLocalFile(str(tmp_path / "a.mp3"))
    engine.buffer = store
    engine.decodedFrames = SAMPLE_RATE * 2
    engine.frame = SAMPLE_RATE
    player.releaseIdleAudio()
    assert store.closed and engine.source().isEmpty()
    assert player.position() == 1000
    player.togglePlay()
    assert loads == [(True, 1000)]
    player.shutdown()


def test_roomKeepsTheSongLoadedDuringAPause(application, tmp_path):
    from app.player import Player
    player = Player()
    player.queue = [{"id": 1, "path": str(tmp_path / "a.mp3"), "title": "A"}]
    player.currentIndex = 0
    player.keepLoaded = True
    engine = player.mediaPlayer
    engine._source = audio_engine.QUrl.fromLocalFile(str(tmp_path / "a.mp3"))
    engine.buffer = PcmStore()
    player.releaseIdleAudio()
    assert not engine.source().isEmpty()
    player.shutdown()


def test_streamLinksSurviveARestartAndCarryTheVideo(monkeypatch, tmp_path):
    from app import config, downloader
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(downloader, "_streamCache", {})
    monkeypatch.setattr(downloader, "_streamCacheLoaded", True)
    expire = int(time.time()) + 6 * 3600
    info = {
        "url": f"https://r1.googlevideo.com/audio?expire={expire}", "duration": 200, "title": "Canzone",
        "webpage_url": "https://www.youtube.com/watch?v=abcdefghijk",
        "formats": [
            {"url": f"https://r1.googlevideo.com/v360?expire={expire}", "height": 360, "vcodec": "avc1.4d", "ext": "mp4", "protocol": "https"},
            {"url": f"https://r1.googlevideo.com/v720?expire={expire}", "height": 720, "vcodec": "avc1.64", "ext": "mp4", "protocol": "https"},
            {"url": f"https://r1.googlevideo.com/v1080?expire={expire}", "height": 1080, "vcodec": "vp9", "ext": "webm", "protocol": "https"},
            {"url": "https://r1.googlevideo.com/a", "vcodec": "none", "ext": "m4a", "protocol": "https"},
        ],
    }
    lookups = []
    monkeypatch.setattr(downloader, "_extract", lambda target: lookups.append(target) or info)
    monkeypatch.setattr(downloader.fast_net, "warmUrl", lambda url: None)
    saved = []
    monkeypatch.setattr(downloader, "_saveStreamCache", lambda: saved.append(True))
    result = downloader.resolveStream("https://www.youtube.com/watch?v=abcdefghijk")
    assert result["url"].startswith("https://r1.googlevideo.com/audio")
    # the background video is taken from the same answer: no second YouTube lookup
    monkeypatch.setattr(downloader, "_runYoutube", lambda *args: (_ for _ in ()).throw(AssertionError("second lookup")))
    assert downloader.resolveVideoStream("https://www.youtube.com/watch?v=abcdefghijk", 1080).endswith(f"v720?expire={expire}")
    assert downloader.resolveVideoStream("https://www.youtube.com/watch?v=abcdefghijk", 480).endswith(f"v360?expire={expire}")
    downloader.markVideoFailed(f"https://r1.googlevideo.com/v720?expire={expire}")
    assert downloader._videoFromCache("https://www.youtube.com/watch?v=abcdefghijk", 1080)["height"] == 360
    # saved to disk and read back by the next run of the app
    with open(os.path.join(str(tmp_path), "stream_cache.json"), "w", encoding="utf-8") as handle:
        json.dump({key: list(value) for key, value in downloader._streamCache.items()}, handle)
    monkeypatch.setattr(downloader, "_streamCache", {})
    monkeypatch.setattr(downloader, "_streamCacheLoaded", False)
    assert downloader.cachedStream("https://www.youtube.com/watch?v=abcdefghijk")["title"] == "Canzone"
    assert lookups == ["https://www.youtube.com/watch?v=abcdefghijk"]


def test_expiredLinksAreNotReused():
    from app import downloader
    past = int(time.time()) - 10
    assert not downloader._cacheValid((time.time(), {"url": f"https://x/videoplayback?expire={past}"}))
    future = int(time.time()) + 3 * 3600
    assert downloader._cacheValid((time.time(), {"url": f"https://x/videoplayback?expire={future}"}))
