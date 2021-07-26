"""
midi to videochess vox wwewewewe
spoocecow 2021
"""

from collections import defaultdict
import functools
import logging
import math
import sys
from typing import List, Dict, Any, Tuple
import funmid

# map a time to a single note
FlatNotes = Dict[int, funmid.MidiNote]

MAX_VOXSTR_LEN = 500
MAX_NOTES = MAX_VOXSTR_LEN + 100


def get_instrument_counts(notes: funmid.Notes) -> Dict[str, int]:
   """
   Get counts of instruments used in the list of notes
   """
   res = defaultdict(int)
   for note in notes:
      if note.is_drums():
         res['Drums'] += 1
      else:
         instr = funmid.midi_instrument_to_str(note.patch)
         res[instr] += 1
   return res


def majority(collection: Dict[Any, int]) -> (int, Any):
   """
   Return the percentage of the collection comprised of the most numerous key.
   """
   maj_key = None
   maj_count = 0
   counts = collection.values()
   total_count = sum(counts)
   for key, count in collection.items():
      if count == max(counts):
         maj_key = key
         maj_count = count
         break
   if maj_key is None:
      return 0, None
   else:
      return (maj_count/total_count) * 100, maj_key


def friendly_print(midi: funmid.SimplyNotes):
   """
   Print all the tracks in this midi in a friendly, informative manner. :polite:
   """
   for trackno in sorted(midi.track_names):
      fmt = '{i}. {track}: {note_n} notes ({instrpct}{instr}, {chanpct}channel {chan})'
      track = midi.by_track()[trackno]
      instrs = get_instrument_counts(track)
      majority_instr = majority(instrs)

      chans = [note.channel for note in track]
      chancounts = {n: chans.count(n) for n in range(16)}
      majority_chan = majority(chancounts)

      print(fmt.format(
         i=trackno,
         track=midi.track_names[trackno],
         note_n=len( track )//2,  # just count ONs
         instrpct='{:.1f}%'.format(majority_instr[0]) if majority_instr[0] != 100 else '',
         instr=majority_instr[1],
         chanpct='{:.1f}%'.format(majority_chan[0]) if majority_chan[0] != 100 else '',
         chan=majority_chan[1]
      ))


def prompt_for_tracks(midi: funmid.SimplyNotes) -> List[int]:
   """
   Get tracks in order of priority from user.
   """
   prios = input("Input desired priority of track #s, comma separated (e.g. 4,2,3). Enter to auto")
   if not prios:
      return sorted(midi.track_names.keys())
   return [int(s) for s in prios.split(',')]


def prompt_for_resolution(midi: funmid.SimplyNotes, selected_tracks: List[int]) -> int:
   """
   Get tick resolution from user.
   """
   gcds = defaultdict(int)
   for track_i, track in sorted(midi.by_track().items()):
      if track_i not in selected_tracks:
         continue
      times = (note.t for note in track)
      gcd = functools.reduce(math.gcd, times)
      gcds[gcd] += 1
      print("Track #{n}: q={q}".format(n=track_i, q=gcd))
   _, most_common_ticks = majority(gcds)
   note_length = 4 * (midi.ticks_per_beat/most_common_ticks)
   print("Detected q: {q} ({nlen}th notes)".format(q=most_common_ticks, nlen=note_length))
   q_log2 = math.log(note_length)
   if q_log2 != math.trunc(q_log2):
      note_length = 2**math.trunc(q_log2)
      most_common_ticks = 4*midi.ticks_per_beat/note_length
      logging.warning("Rounding detected to longer power of 2: {q} ({nlen}th notes)".format(q=most_common_ticks, nlen=note_length))
   inp = input("Input desired resolution, or hit Enter to accept default ({q}): ".format(q=most_common_ticks))
   if inp:
      return int(inp)
   else:
      return most_common_ticks


def prompt_for_time_slice(midi: funmid.SimplyNotes, selected_tracks: List[int]) -> (int, int):
   """
   Get desired section of song from user, default whole thing.
   """
   min_t = 2**31
   max_t = 0
   for track_i, track in sorted(midi.by_track().items()):
      if track_i not in selected_tracks:
         continue
      times = [note.t for note in track if note.what in (funmid.MidiNote.NOTE_ON, funmid.MidiNote.NOTE_OFF)]
      min_t = min(min_t, min(times))
      max_t = max(max_t, max(times))
   min_final = min_t
   max_final = max_t
   if 'y' in input("Input desired time slices? (y/N)").lower():
      inp = input("Slice from? [default: {min}, {minclock}] ".format(min=min_t, minclock=midi.tick_to_mmss(min_t)))
      if inp:
         min_final = max(min_t, int(inp))
      inp = input("Slice to? [default: {max}, {maxclock}] ".format(max=max_t, maxclock=midi.tick_to_mmss(max_t)))
      if inp:
         max_final = min(max_t, int(inp))
   return min_final, max_final


def scale(midi: funmid.SimplyNotes, track_priority: List[int], time_slice: Tuple[int, int]) -> funmid.SimplyNotes:
   """
   Normalize track note values around closest C. vox ain't handle more than two octaves.
   """
   final = []
   tracks = midi.by_track()
   time_start, time_end = time_slice
   for track_n, original_notes in tracks.items():
      if track_n not in track_priority:
         # user deselected this, don't include it
         continue
      if funmid.is_percussion(original_notes):
         # do not adjust percussion, just do time slicing
         new_notes = [old for old in original_notes if time_start <= old.t <= time_end]
         final.extend(new_notes)
         continue

      # capture all note beginnings in the desired time frame
      note_values = [note.note for note in original_notes
         if note.what == funmid.MidiNote.NOTE_ON and time_start <= note.t <= time_end
      ]
      low, high = min(note_values), max(note_values)
      lowest_c = int(low/12.0)*12
      base = lowest_c
      if high - base > 25:
         # possibly too wide of a range to capture melody :/
         highest_c = int(math.ceil(high/12.0))*12
         logging.warning(f"GUP BOH, too big range in track #{track_n} [{low}-{high}] (C range {lowest_c}-{highest_c})")
         if highest_c - high < low - lowest_c:
            base = highest_c - 24
            print(f"Using (high C - 24) [{base}] as base instead")
      # copy notes using adjusted base (and time slice)
      new_notes = [old.copy(note=max(0, old.note-base)) for old in original_notes if time_start <= old.t <= time_end]
      final.extend(new_notes)
   return midi.copy(notes=final)


def flatten(midi: funmid.SimplyNotes, priorities: List[int]) -> FlatNotes:
   """
   Remove chords/collisions so only one note starts at any given time.
   """
   final = {}
   for t, notes in midi.by_time().items():
      notes_by_prio = sorted(notes, key=lambda note: priorities.index(note.track))
      final[t] = notes_by_prio[0]
   return final


def quantize_to_beat(notes: FlatNotes, quantize_to: int) -> FlatNotes:
   """
   Remove notes that don't fit into the given beat (or insert rests if nothing playing on beat).
   """
   t = 0
   final = {}
   pool = notes.copy()
   while t < max(pool.keys()):
      if len(final) > MAX_NOTES:
         break
      p2 = sorted(pool.copy())
      for nt in sorted(p2):
         n = pool[nt]
         if nt+n.dur < t:
            pool.pop(nt)
      nt = sorted(pool)[0]
      next_note = pool[nt]

      if nt <= t < nt+next_note.dur:
         # TODO could figure out durations better here
         final[t] = next_note
         pool.pop(nt)
      else:
         final[t] = funmid.MidiNote()  # empty/rest
      t += quantize_to
   return final



def crunch(midi: funmid.SimplyNotes, track_priority: List[int], tick_quantize: int, time_slice: Tuple[int, int]) -> FlatNotes:
   """
   Smush all desired tracks together into a single flat list.
   """
   scale_corrected_notes = scale(midi, track_priority, time_slice)
   flat_notes = flatten(scale_corrected_notes, track_priority)
   return quantize_to_beat(flat_notes, tick_quantize)


def get_vox_instrument(note: funmid.MidiNote) -> str:
   """Convert a general midi patch to a vox instrument"""
   if note.is_drums():
      return '<drums>'
   patch = note.patch
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

def get_vox_pitch(note: int, vox_instr:str='n1', is_percussion=False) -> str:
   """Convert a note (length ignored) to a vox string"""

   scales = [
      '-10', '-9', '-9', '-8', '-7', '-7', '-6', '-5', '-4', '-3', '-2', '-', '',
      '+-', '+', '+2', '+3-', '+4-', '+5', '+6', '+7', '+8', '+9', '+10'
   ]
   if not is_percussion:
      if note >= len(scales):
         scale_s = '+10'
      elif note < 0:
         scale_s = '-10'
      else:
         scale_s = scales[note]

      return vox_instr + scale_s

   # special percussion handlin waow
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


def note_to_vox(note: funmid.MidiNote) -> str:
   if note.is_drums():
      return get_vox_pitch(note.note, is_percussion=True)
   else:
      return get_vox_pitch(note.note, vox_instr=get_vox_instrument(note), is_percussion=False)


def build_voxstr(notes: FlatNotes, bpm:int, note_len: int) -> str:
   s = f'^song ^bpm={bpm} ^l={note_len}'
   lastnote = None
   for t in sorted(notes.keys()):
      note = notes[t]
      if note.is_rest():
         if lastnote:
            if s[-1] not in ' .':
               s += ' '
            s += '.'
         else:
            # don't add rests at start like a lot of annoying midis do >:C
            pass
      else:
         if lastnote and note_to_vox(note) == note_to_vox(lastnote):
            note_s = '*'
         elif lastnote and get_vox_instrument(note) == get_vox_instrument(note):
            note_s = get_vox_pitch(note.note, '*', note.is_drums())
            if note_s == '*':
               # reset to middle C needs +0
               note_s = '*+0'
         else:
            note_s = note_to_vox(note)
         if note_s:
            print(note_s + ' ', end='')
            s += ' ' + note_s
            lastnote = note
      if len(s) > MAX_VOXSTR_LEN:
         break
   return s

def main(fn=r"ta-poochie.mid"):
   midifile = funmid.MidiFile(fn)
   midi = midifile.to_simplynotes()

   # Collect info from user
   print(fn)
   print('='*40)
   friendly_print(midi)
   trax = prompt_for_tracks(midi)
   tick_quantize = prompt_for_resolution(midi, trax)
   time_slice = prompt_for_time_slice(midi, trax)

   # do some sanity checkin'
   min_note_length = 4*(midi.ticks_per_beat/tick_quantize)
   if min_note_length > 32:
      midi.bpm *= (min_note_length/32)
      min_note_length = 32
      print("Notes are too short, increasing bpm to {bpm}".format(bpm=midi.bpm))
   if midi.bpm > 480:
      tick_quantize *= (midi.bpm/480)
      midi.bpm = 480
      print("BPM too high, increasing tick quantization to {q}".format(q=tick_quantize))

   # Param processing done, time to build voxstr
   final_notes = crunch(midi, trax, tick_quantize, time_slice)
   voxstr = build_voxstr(final_notes, midi.bpm, min_note_length)

   return voxstr


if __name__ == "__main__":
   if len(sys.argv) == 2:
      fn = sys.argv[1]
   else:
      fn = input("filename pls").strip('"')
   wee = main(fn)
   with open(r"C:\tmp\vox.txt", "w") as f:
      f.write(wee + '\n')
