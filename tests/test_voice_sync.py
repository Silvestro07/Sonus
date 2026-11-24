import random

import pytest

from app import voice_sync


def test_tapsInRhythmGiveTheDelayWithoutReactionTime():
    beats = [10000 + index * voice_sync.BEAT_MS for index in range(voice_sync.BEATS)]
    generator = random.Random(4)
    taps = [beat + 230 + generator.uniform(-25, 25) for beat in beats]
    value, error = voice_sync.measure(taps, beats)
    assert error is None and abs(value - 230) < 20
    # a tap slightly early still belongs to its beat, the first two are ignored (getting into the rhythm)
    assert voice_sync.tapOffsets([beats[2] - 60, beats[3] + 10], beats) == [-60, 10]
    assert voice_sync.tapOffsets([beats[0] + 5], beats) == []


def test_tooFewOrRandomTapsAskToRepeat():
    beats = [index * 1000 for index in range(8)]
    assert voice_sync.measure([2100, 3100], beats)[0] is None
    value, error = voice_sync.measure([2050, 3600, 4100, 5700, 6000, 7550], beats)
    assert value is None and "irregolari" in error


def test_choicesAreExactInOneDirectionOrSplitInHalf():
    myNeed, theirNeed = 260, 140
    assert voice_sync.delaysFor(voice_sync.MODE_ME, myNeed, theirNeed) == (260, 0)
    assert voice_sync.mismatch(voice_sync.MODE_ME, myNeed, theirNeed) == (0, 400)
    assert voice_sync.delaysFor(voice_sync.MODE_THEM, myNeed, theirNeed) == (0, 140)
    assert voice_sync.mismatch(voice_sync.MODE_THEM, myNeed, theirNeed) == (400, 0)
    assert voice_sync.mismatch(voice_sync.MODE_HALF, myNeed, theirNeed) == (200, 200)


def test_planIsConvertedToMyClock():
    plan = voice_sync.makePlan("a", "b", 50000)
    assert [phase["kind"] for phase in plan["phases"]] == ["calibrate", "singer", "singer"]
    assert plan["phases"][1]["singer"] == "a" and plan["phases"][2]["singer"] == "b"
    mine = voice_sync.planInMyClock(plan, 300)
    assert mine["phases"][0]["beats"][0] == 49700
    assert voice_sync.myRole(mine["phases"][1], "b") == "listen"
    assert voice_sync.myRole(mine["phases"][2], "b") == "sing"


class FakeLink:
    def __init__(self):
        self.other = None
        self.sent = []

    def publish(self, code, subtopic, payload, retain=False):
        self.sent.append(payload)
        if self.other is not None:
            self.other._onReceived(code, subtopic, payload)

    def isConnected(self):
        return True


@pytest.fixture
def pair(monkeypatch, tmp_path):
    from PySide6.QtCore import QCoreApplication
    QCoreApplication.instance() or QCoreApplication([])
    from app.player import Player
    from app.together import TogetherController
    controllers = []
    for name in ("a", "b"):
        player = Player()
        cues = []
        player.mediaPlayer.scheduleCues = lambda times, accents=None, cues=cues: cues.extend(times) or True
        controller = TogetherController(player, None, lambda song: {}, clientId=name, profile={"name": name.upper(), "photo": ""})
        controller.link = FakeLink()
        controller.code = "SONUS-TEST"
        controller.delayOverride = 0
        controller.cues = cues
        controllers.append(controller)
    first, second = controllers
    first.link.other, second.link.other = second, first
    first.peers = {"a": {"id": "a", "name": "A"}, "b": {"id": "b", "name": "B"}}
    second.peers = dict(first.peers)
    yield first, second
    for controller in controllers:
        controller.voiceSyncTimer.stop()
        controller.player.shutdown()


def _tapPhase(controller, role, offset):
    phase = next(item for item in controller.voiceSync["phases"] if item["role"] == role)
    for beat in phase["beats"]:
        controller.voiceSyncTap(beat + offset)


def test_twoFriendsMeasureEachOtherAndApplyTheChoice(pair):
    first, second = pair
    assert first.startVoiceSync("b")
    assert second.voiceSync and second.voiceSync["partner"] == "a" and not second.voiceSync["initiator"]
    # each app ticks in the test round and in its own turn only (8 + 8 clicks), never while the friend sings
    assert len(first.cues) == 16 and len(second.cues) == 16
    _tapPhase(first, "click", 20)
    _tapPhase(first, "listen", 250)
    _tapPhase(second, "click", 40)
    _tapPhase(second, "listen", 180)
    first._finishVoiceSyncTaps()
    assert first.voiceSync["status"] == "waiting" and first.voiceSync["myNeed"] == 230
    second._finishVoiceSyncTaps()
    assert first.voiceSync["status"] == "done" and second.voiceSync["status"] == "done"
    assert first.voiceSync["theirNeed"] == 140 and second.voiceSync["theirNeed"] == 230
    first.applyVoiceSync(voice_sync.MODE_ME)
    assert first.delayMs() == 230 and second.delayMs() == 0
    assert first.preciseSync() and first.driftTolerance() < 200
    assert first.voiceSync["status"] == "applied" and second.voiceSync["status"] == "applied"
    first.setPreciseSync(False)


def test_failedMeasureIsReportedToTheFriend(pair):
    first, second = pair
    first.startVoiceSync("b")
    _tapPhase(second, "click", 30)
    _tapPhase(second, "listen", 200)
    first._finishVoiceSyncTaps()
    assert first.voiceSync["status"] == "failed"
    assert second.voiceSync["status"] == "failed" and "A" in second.voiceSync["error"]


def test_cancelStopsBothSides(pair):
    first, second = pair
    first.startVoiceSync("b")
    second.cancelVoiceSync(notifyPartner=True)
    assert first.voiceSync is None and second.voiceSync is None


def test_dialogFollowsTheMeasureAndOffersTheChoices(pair):
    from PySide6.QtWidgets import QApplication
    if not isinstance(QApplication.instance(), QApplication):
        pytest.skip("needs widgets")
    from app.ui.voice_sync_dialog import VoiceSyncDialog
    first, second = pair
    first.startVoiceSync("b")
    dialog = VoiceSyncDialog(first)
    dialog._tick()
    assert "Prova" in dialog.instructionLabel.text() and "Passo 1 di 3" == dialog.stepLabel.text()
    _tapPhase(first, "click", 20)
    _tapPhase(first, "listen", 250)
    _tapPhase(second, "click", 40)
    _tapPhase(second, "listen", 180)
    first._finishVoiceSyncTaps()
    second._finishVoiceSyncTaps()
    labels = [button.text() for mode, button in dialog.choiceButtons if not button.isHidden()]
    assert len(labels) == 3 and "Io sento B a tempo" in labels[0]
    dialog.choiceButtons[0][1].click()
    assert "+0.23 s" in dialog.resultLabel.text()
    first.setPreciseSync(False)
    dialog.close()
