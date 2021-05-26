"""midi to videochess vox tehe"""

import functools
import itertools
import math
import mido
from typing import List, Dict

Note = mido.Message
Notes = List[Note]

class FlatNote:
    t = 0
    duration = 0
    note = 0
    channel = 0
    instrument = 'n1'

    def __init__(self, t:int, note:int=0, channel:int=0, is_percussion:bool=False):
        self.t = t
        self.duration = 0
        self.note = note
        self.channel = channel
        self.is_percussion = is_percussion
        self.instrument = 'n1'

    def is_rest(self):
        return self.duration == 0

    def __str__(self):
        return 'FN<t=%d-%d n%d c%d[%s] %s>' % (
            self.t, self.t+self.duration, self.note, self.channel, self.instrument, 'D' if self.is_percussion else 'n'
        )

FlatNotes = Dict[int, FlatNote]
Track = mido.MidiTrack
Tracks = List[Track]
PrioTracks = Dict[int, Track]

def get_bpm(midi: mido.MidiFile) -> int:
    """Get (initial) bpm of midi file"""
    assert midi.type in [0,1], "async files r wack"
    for track in midi.tracks:
        assert isinstance(track, mido.MidiTrack)
        for msg in track:
            assert isinstance(msg, mido.messages.BaseMessage)
            if msg.dict().get('type', '') == 'set_tempo' and hasattr(msg, 'tempo'):
                return mido.tempo2bpm(msg.tempo)
    return 120


def get_track_names(midi: mido.MidiFile) -> list:
    return [t.name for t in midi.tracks]


def get_track_patch(track: mido.MidiTrack) -> int:
    for n in track:
        if not n.is_meta and n.type == 'program_change':
            return n.program
    return -1


def track_to_abs_notes(track: mido.MidiTrack, is_percussion=False) -> FlatNotes:
    """Flatten track notes into absolute time and relative values"""
    notes = [msg for msg in track if not msg.is_meta]

    note_vals = [note.note for note in notes if note.type == 'note_on' and note.velocity > 0]
    if not note_vals:
        return {}
    # find lowest multiple of 12 (C) to use as base
    lowest_note = min(note_vals)
    highest_note = max(note_vals)
    lowest_c = int(lowest_note/12.0)*12
    base = lowest_c
    if highest_note - base > 25:
        highest_c = int(math.ceil(highest_note/12.0))*12
        print("GUP BOH, too big range in %s [%d-%d] (lowest_c:%d highest_c:%d)" % (track.name, lowest_note, highest_note, lowest_c, highest_c))
        if highest_c - highest_note < lowest_note - lowest_c:
            base = highest_c - 24
            print("Using highest C - 24 as base instead: %d" % base)

    t = 0
    instr = 'n1'
    prevnote = FlatNote(0)
    ticks = dict()
    its_drums = is_percussion
    for note in notes:
        t += note.time
        if note.type == 'program_change':
            print("lala", note)
            if note.channel == 9:
                its_drums = True
                instr = '<drums>'
            else:
                instr = get_vox_instrument(note.program+1)
            print("Setting instrument for %s (channel %d) to %s" % (track.name, note.channel, instr))
        elif note.type == 'control_change' and note.channel == 9:
            its_drums = True
            instr = '<drum>'
        elif note.type == 'note_on' and note.velocity > 0:
            if its_drums:
                # do not scale note, we'll deal with it later
                adjusted_note = note.note
            else:
                adjusted_note = max(0, note.note-base)
            prevnote = FlatNote(t, adjusted_note, note.channel, its_drums)
        elif ((note.type == 'note_on' and note.velocity == 0) or note.type == 'note_off') and prevnote.t not in ticks:
            # note finished
            prevnote.duration = t - prevnote.t
            prevnote.instrument = instr
            ticks[prevnote.t] = prevnote
    return ticks


def flatten_tracks(tracks: PrioTracks) -> FlatNotes:
    final = dict()
    for prio in sorted(tracks.keys()):
        track = tracks[prio]
        flatnotes = track_to_abs_notes(track, is_percussion='Drum' in track.name or prio==99)
        if not flatnotes:
            continue
        for t in sorted(flatnotes.keys()):
            m = flatnotes[t]
            if t not in final:
                final[t] = m
    return final


def quantize_to_beat(notes: FlatNotes, quantize_to=-1) -> FlatNotes:
    if quantize_to <= 0:
        # find the most common distance between notes and quantize to that
        quantize_to = functools.reduce(math.gcd, sorted(notes.keys()))
    t = 0
    final = {}
    pool = notes.copy()
    while t < max(pool.keys()):
        p2 = sorted(pool.copy())
        for nt in sorted(p2):
            n = pool[nt]
            if nt+n.duration < t:
                pool.pop(nt)
        nt = sorted(pool)[0]
        next_note = pool[nt]
        if nt <= t < nt+next_note.duration:
            # TODO could figure out durations better here
        #if pool.get(t):
            final[t] = next_note
            pool.pop(nt)
        else:
            final[t] = FlatNote(t)
        t += quantize_to
    return final

def get_vox_instrument(patch:int) -> str:
    """Convert a general midi patch to a vox instrument"""
    if patch <= 16:  # pianos n such
        return 'n5'  # yossynote
    elif patch <= 24: # organs
        return 'n2'   # catnote
    elif patch <= 29: # acoustic guitar
        return 'n8'   # dantnote
    elif patch <= 32: # electric guitar
        return 'n4'   # dootnote
    elif patch <= 40: # bass
        return 'n10'  # slapnote
    elif patch in (46, 59): # pizzicato, tuba
        return 'n7'         # bupnote
    elif patch <= 47: # string
        return 'n13'   # shynote
    elif patch == 48:  # timpani
        return 'd2'    # kick
    elif patch <= 52:  # strings
        return 'n2'    # catnote
    elif patch <= 55:  # choir
        return 'n9'    # cursed downote
    elif patch == 56:  # orch hit
        return 'n12'   # orchnote
    elif patch <= 72:  # brass
        return 'n1'    # cnote
    elif patch <= 80:  # winds
        return 'n11'   # jarnote
    elif patch in (116, 118, 119): # toms etc
        return 'd2'    # kick
    else:
        # idk there are 11 kk notes just use those
        return 'kk%d' % (1+int((patch-80)/(48/11)))

def note_to_vox(note: int, vox_instr:str='n1', is_percussion=False) -> str:
    """Convert a note (length ignored) to a vox string"""

    scales = [
        '-10', '-9', '-9', '-8', '-7', '-7', '-6', '-5', '-4', '-3', '-2', '-', '',
        '+-', '+', '+2', '+3-', '+4-', '+5', '+6', '+7', '+8', '+9', '+10'
    ]
    if note >= len(scales):
        scale = '+10'
    elif note < 0:
        scale = '-10'
    else:
        scale = scales[note]

    if is_percussion:
        if note == 79:  # low cuica
            return 'n3'
        elif note == 78:  # high cuica
            return 'n3+6'
        if note in (82, 81, 70, 69, 54, 51, 46):  # triangle, maracas, cabasa, tambourine, ride, hi hat
            return "'s"
        elif note in (80, 59, 44, 42):  # mute triangle, ride, hi hats
            return "kk14"
        elif note in (57, 49):  # crash cymbals
            return 'kk14-10'
        elif note in (50, 48, 47, 45, 43, 41):  # toms
            return 'd2+%d' % (5+(note-40)/2)
        elif note in (40, 38):  # snares
            return 'd1'
        elif note in (39, 30, 29):  # clap/scratch
            return 'd3'
        elif note == 37:  # side stick
            return 'kk12'
        elif note in (36, 35):   # bass drum
            return 'd2'
        else:
            # probably not important
            print("No note for percussion: %d" % note)
            return ''
    else:
        return vox_instr + scale


def fn_to_vox(fn:str, quantize_to=-1) -> str:
    f = mido.MidiFile(fn)
    bpm = get_bpm(f)
    print("BPM: %d  Ticks per beat: %d" % (bpm, f.ticks_per_beat))
    qs = {}
    good_tracks = []
    for t in f.tracks:
        qnotes = track_to_abs_notes(t)
        if not qnotes:
            continue
        good_tracks.append(t)
        q = functools.reduce(math.gcd, qnotes)
        print("gcd of %s: %d" % (t.name, q))
        if q not in qs:
            qs[q] = 0
        else:
            qs[q] += 1
    most_common_q = f.ticks_per_beat
    print("qtr note: %d ticks" % most_common_q)
    for k,v in qs.items():
        if v == max(qs.values()):
            most_common_q = k
            break
    note_length = 4*(f.ticks_per_beat/most_common_q)
    print("Detected q: %d (%dth notes)" % (most_common_q, note_length))
    q_log2 = math.log(note_length,2)
    if q_log2 != math.trunc(q_log2):
        note_length = 2**math.trunc(q_log2)
        most_common_q = 4*f.ticks_per_beat/note_length
        #note_length = 4*(f.ticks_per_beat/most_common_q)
        print("Rounding detected to longer power of 2: %d (%dth notes)" % (most_common_q, note_length))
    if quantize_to <= 0:
        quantize_to = most_common_q
    note_length = 4*(f.ticks_per_beat/quantize_to)
    print("Applied q: %d (%dth notes)" % (quantize_to, note_length))
    if note_length > 32:
        bpm = bpm * (note_length / 32)
        print("Too tiny notes, increasing bpm to %d" % bpm)
        note_length = 32
    prios = {}
    for t in good_tracks:
        n = input("Enter priority for Track `%s` patch %d (enter to skip, 99 for drums): " % (t.name, get_track_patch(t)))
        if n:
            prios[int(n)] = t
    flat = flatten_tracks(prios)

    final = quantize_to_beat(flat, quantize_to)
    s= '^song ^bpm=%d ^l=%d' % (bpm, note_length)

    lastinst = ''
    for t in sorted(final.keys()):
        note = final[t]
        if note.is_rest():
            if lastinst:
                s += '.'
            else:
                # don't add rests at start like a lot of annoying midis do >:C
                pass
        else:
            voxnote = note.instrument
            # if voxnote == lastinst:
            #     voxnote = '*'
            # else:
            #     lastinst = voxnote
            note_s = note_to_vox(note.note, voxnote, note.is_percussion)
            if note_s:
                s += ' ' + note_s
        if len(s) > 1000:
            break
    return s

def fast(fn, q=-1):
    with open(r"C:\tmp\vox.txt", "w") as f:
        f.write( fn_to_vox(fn, q) + '\n' )

import sys

if __name__ == "__main__":
    if len(sys.argv) == 2:
        fast(sys.argv[1])
    elif len(sys.argv) == 3:
        fast(sys.argv[1], int(sys.argv[2]))
    else:
        fn = input("filename NOW:").strip('"')
        q = input("q?") or '0'
        fast(fn, int(q))