"""Sincronizza voci: measures how late each person hears the other on a voice call, so you can sing together.

How it works (two people in a room, A starts it):
  0. "Prova" - both apps tick a click every second and each person taps along with THEIR OWN clicks.
     This measures each one's own audio output delay + how early/late that person taps (personal bias).
  1. A's turn - only A's app ticks; A says "ta" on every click. B hears A through the call and taps along.
  2. B's turn - the opposite.
Everybody taps in rhythm (not as a reaction to a sound), so reaction time does not count.
The click times are on the room's shared clock (same as the music), so what B measures in step 1 minus B's own
bias is exactly how much later than the room B's music must be to hear A's voice on the beat ("X_B").

Physics allows a perfect match in one direction only (a voice needs time to travel both ways), so the result
offers: "I hear my friend in time", "my friend hears me in time" or half and half.
"""
import statistics
import uuid

BEAT_MS = 1000
BEATS = 8
SKIP_BEATS = 2          # the first taps are for getting into the rhythm
COUNTDOWN_MS = 4000
PHASE_GAP_MS = 2500
EARLY_MS = 150          # a tap up to this much before its beat still belongs to it
MIN_TAPS = 3
MAX_SPREAD_MS = 180     # taps scattered more than this: measure again
MAX_DELAY_MS = 3000

PHASE_CALIBRATE = "calibrate"
PHASE_SINGER = "singer"

MODE_ME = "me"          # I hear the other in time
MODE_THEM = "them"      # the other hears me in time
MODE_HALF = "half"


def newSession():
    return uuid.uuid4().hex[:10]


def makePlan(initiatorId, partnerId, startAt, beatMs=BEAT_MS, beats=BEATS):
    """Phases with their beat times in the initiator's clock (ms)."""
    phases = []
    at = startAt
    for kind, singer in ((PHASE_CALIBRATE, None), (PHASE_SINGER, initiatorId), (PHASE_SINGER, partnerId)):
        phases.append({"kind": kind, "singer": singer, "beats": [at + index * beatMs for index in range(beats)]})
        at += beats * beatMs + PHASE_GAP_MS
    return {"initiator": initiatorId, "partner": partnerId, "beatMs": beatMs, "phases": phases}


def planInMyClock(plan, offsetMs):
    """offsetMs = initiator clock - my clock (as ClockSync gives it)."""
    converted = dict(plan)
    converted["phases"] = [dict(phase, beats=[beat - offsetMs for beat in phase["beats"]]) for phase in plan["phases"]]
    return converted


def myRole(phase, myId):
    """'click' = my app ticks and I tap/say ta on my clicks; 'sing' = my app ticks and I say "ta";
    'listen' = no clicks for me, I tap along with my friend's voice."""
    if phase["kind"] == PHASE_CALIBRATE:
        return "click"
    return "sing" if phase["singer"] == myId else "listen"


def tapOffsets(taps, beats, beatMs=BEAT_MS):
    """Each tap minus the beat it belongs to (the last beat at most EARLY_MS after it)."""
    if not beats:
        return []
    offsets = {}
    first = beats[0]
    for tap in taps:
        index = int((tap - first + EARLY_MS) // beatMs)
        if index < SKIP_BEATS or index >= len(beats):
            continue
        offset = tap - beats[index]
        # a double tap on the same beat: keep the first
        offsets.setdefault(index, offset)
    return [offsets[index] for index in sorted(offsets)]


def measure(taps, beats, beatMs=BEAT_MS):
    """Median offset of the taps, or None with the reason when the taps are too few or too scattered."""
    offsets = tapOffsets(taps, beats, beatMs)
    if len(offsets) < MIN_TAPS:
        return None, "Pochi tocchi: tocca a ogni colpo che senti"
    median = statistics.median(offsets)
    spread = statistics.median([abs(value - median) for value in offsets]) * 1.4826
    if spread > MAX_SPREAD_MS:
        return None, "Tocchi troppo irregolari: prova a tenere il ritmo"
    return median, None


def listenDelay(listenOffset, ownBias):
    """How much later than the room this person's music must be to hear the other's voice on the beat."""
    return max(-MAX_DELAY_MS, min(MAX_DELAY_MS, listenOffset - ownBias))


def delaysFor(mode, myNeed, theirNeed):
    """(my delay, their delay) in ms for a choice. myNeed/theirNeed = listenDelay of each person."""
    if mode == MODE_ME:
        relative = myNeed
    elif mode == MODE_THEM:
        relative = -theirNeed
    else:
        relative = (myNeed - theirNeed) / 2
    relative = int(round(max(-MAX_DELAY_MS, min(MAX_DELAY_MS, relative))))
    return max(0, relative), max(0, -relative)


def mismatch(mode, myNeed, theirNeed):
    """How late (ms) each one hears the other after applying a choice: (for me, for them)."""
    mine, theirs = delaysFor(mode, myNeed, theirNeed)
    relative = mine - theirs
    return int(round(myNeed - relative)), int(round(theirNeed + relative))
