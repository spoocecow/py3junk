"""midi to videochess vox tehe"""

import functools
import itertools
import math
import mido
from typing import List, Tuple, Dict

Note = mido.Message
Notes = List[Note]
FlatNote = Tuple[int, Note]
FlatNotes = Dict[int, Tuple[FlatNote, bool]]
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
    ticks = dict()
    for note in notes:
        t += note.time
        if note.type == 'note_on' and note.velocity > 0:
            if is_percussion:
                # do not scale note, we'll deal with it later
                adjusted_note = note.copy()
            else:
                adjusted_note = note.copy(note=max(0,note.note-base))
            ticks[t] = (adjusted_note, is_percussion)
    return ticks


def flatten_tracks(tracks: PrioTracks) -> FlatNotes:
    final = dict()
    for prio in sorted(tracks.keys()):
        track = tracks[prio]
        flatnotes = track_to_abs_notes(track, is_percussion='Drum' in track.name or prio==99)
        # TODO quantize here, or once flattened? CAN we quantize here?
        if not flatnotes:
            continue
        for t in sorted(flatnotes.keys()):
            m = flatnotes[t]
            if t not in final:
                final[t] = m
    return final


def get_base_ticks(notes: FlatNotes, ticks_per_beat=192) -> int:
    return functools.reduce(math.gcd, sorted(notes.keys()))


def quantize_to_beat(notes: FlatNotes, quantize_to=-1) -> FlatNotes:
    if quantize_to <= 0:
        # find the most common distance between notes and quantize to that
        quantize_to = functools.reduce(math.gcd, sorted(notes.keys()))
    t = 0
    final = {}
    pool = notes.copy()
    while t < max(notes.keys()):
        if pool.get(t):
            final[t] = pool.pop(t)
        else:
            final[t] = (mido.Message(type='note_on', time=t, velocity=0), False)
        t += quantize_to
    return final


def note_to_vox(note: int, vox_instr:str='n1', is_percussion=False) -> str:
    """Convert a note (length ignored) to a vox string"""

    scales = [
        '-10', '-9', '-9', '-8', '-7', '-7', '-6', '-5', '-4', '-3', '-2', '-', '',
        '+-', '+', '+2', '+3-', '+4-', '+5', '+6', '+7', '+8', '+9', '+10'
    ]
    if note > len(scales):
        scale = '+10'
    else:
        scale = scales[note]

    if is_percussion:
        if note == 79:  # low cuica
            return 'n3'
        elif note == 78:  # high cuica
            return 'n3+6'
        if note in (81, 80, 70, 69, 54, 51):  # triangles, maracas, cabasa, tambourine, ride
            return "'s"
        elif note in (59, 46, 44, 42):  # ride, hi hats
            return "kk14"
        elif note in (50, 48, 47, 45, 43, 41):  # toms
            return 'd2+%d' % (5+(note-40)/2)
        elif note in (40, 38):  # snares
            return 'd1'
        elif note in (39, 30, 29):  # clap/scratch
            return 'd3'
        elif note in (36, 35):   # bass drum
            return 'd2'
        else:
            # probably not important
            print("No note for percussion: %d" % note)
            return ''
    else:
        return vox_instr + scale


def fn_to_vox(fn:str, q=-1) -> str:
    f = mido.MidiFile(fn)
    prios = {}
    for t in f.tracks:
        n = input("Enter priority for Track `%s` (enter to skip, 99 for drums): " % t.name)
        if n:
            prios[int(n)] = t
    #prios = {i:n for i,n in enumerate(f.tracks)}
    flat = flatten_tracks(prios)  # TODO need to still keep tracks separated so drums can be identified...
    final = quantize_to_beat(flat, q)
    s= '^song ^bpm=%d' % get_bpm(f)

    for t in sorted(final.keys()):
        note, is_percussion = final[t]
        if note.velocity == 0:
            s += '.'
        else:
            s += ' %s' % note_to_vox(note.note, 'n%d' % (note.channel), is_percussion)
    return s