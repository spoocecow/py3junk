"""
midi to videochess vox wwewewewe
spoocecow 2021
"""

from collections import defaultdict
import functools
import logging
import math
import sys
import random
from typing import List, Dict, Any, Tuple
import funmid

# map a time to a single note
FlatNotes = Dict[int, funmid.MidiNote]

MAX_VOXSTR_LEN = 500
MAX_NOTES = MAX_VOXSTR_LEN * 2

g_ChangeLengths = True
g_GrimeFactor = 10


class LengthChange(funmid.MidiNote):

   INC = 111
   DEC = 222

   def __init__(self, t, what=INC):
      funmid.MidiNote.__init__(self)
      self.t = t
      self.what = what

   def __repr__(self):
      return '<N len ' + ('INC' if self.what == LengthChange.INC else 'DEC') + '>'


class BPMChange(funmid.MidiNote):

   BPM_CHANGE = 333

   def __init__(self, t, new_bpm):
      funmid.MidiNote.__init__(self)
      self.what = BPMChange.BPM_CHANGE
      self.t = t
      self.note = new_bpm

   def __repr__(self):
      return '<N bpm:=%d>' % self.note


def get_instrument_counts(notes: funmid.Notes) -> Dict[str, int]:
   """
   Get counts of instruments used in the list of notes
   """
   res = defaultdict( int )
   for note in notes:
      if note.is_drums():
         res['Drums'] += 1
      else:
         instr = funmid.midi_instrument_to_str( note.patch )
         res[instr] += 1
   return res


def majority(collection: Dict[Any, int]) -> (int, Any):
   """
   Return the percentage of the collection comprised of the most numerous key.
   """
   maj_key = None
   maj_count = 0
   counts = collection.values()
   total_count = sum( counts )
   for key, count in collection.items():
      if count == max( counts ):
         maj_key = key
         maj_count = count
         break
   if maj_key is None:
      return 0, None
   else:
      return (maj_count / total_count) * 100, maj_key


def friendly_print(midi: funmid.SimplyNotes):
   """
   Print all the tracks in this midi in a friendly, informative manner. :polite:
   """
   max_track_w = max(map(len, midi.track_names.values()))
   for trackno in sorted( midi.track_names ):
      fmt = '{i:>2}. {track:<{trackw}}: {note_n} notes ({instrpct}{instr}, {chanpct}channel {chan})'
      track = midi.by_track()[trackno]
      instrs = get_instrument_counts( track )
      majority_instr = majority( instrs )

      chans = [note.channel for note in track]
      chancounts = { n: chans.count( n ) for n in range( 16 ) }
      majority_chan = majority( chancounts )

      print( fmt.format(
         i=trackno,
         track=midi.track_names[trackno],
         trackw=max_track_w,
         note_n=len( track ) // 2,  # just count ONs
         instrpct='{:.1f}%'.format( majority_instr[0] ) if majority_instr[0] != 100 else '',
         instr=majority_instr[1],
         chanpct='{:.1f}%'.format( majority_chan[0] ) if majority_chan[0] != 100 else '',
         chan=majority_chan[1]
      ) )


def prompt_for_tracks(midi: funmid.SimplyNotes) -> List[int]:
   """
   Get tracks in order of priority from user.
   """
   prios = input( "Input desired priority of track #s, comma separated (e.g. 4,2,3). Or, press enter to accept all in current order: " )
   if not prios:
      return sorted( midi.track_names.keys() )
   return [int( s ) for s in prios.split( ',' )]


def prompt_for_resolution(midi: funmid.SimplyNotes, selected_tracks: List[int]) -> int:
   """
   Get tick resolution from user.
   """
   gcds = defaultdict( int )
   print("Default q: {}".format(midi.ticks_per_beat / 4))
   for track_i, track in sorted( midi.by_track().items() ):
      if track_i not in selected_tracks:
         continue
      # find all note on/off events (what we really care about) and find their greatest common time divisor
      # to use as the minimum vox note length
      times = (note.t for note in track if note.is_edge())
      gcd = functools.reduce( math.gcd, times )
      gcds[gcd] += 1
      print( "Track #{n}: q={q};".format( n=track_i, q=gcd ), end=' ' )
   print()
   _, most_common_ticks = majority( gcds )
   note_length = int( 4 * (midi.ticks_per_beat / most_common_ticks) )
   print( "BPM: {bpm} Detected q: {q} ({nlen}th notes)".format( bpm=midi.bpm, q=most_common_ticks, nlen=note_length ) )

   # gcd can get screwed up especially in format 0 midis, e.g. gcd becomes 1 tick which is useless
   # try to at least get it to nearest power of 2
   q_log2 = math.log( note_length, 2 )
   while q_log2 != math.trunc( q_log2 ):
      note_length = int( 2 ** math.trunc( q_log2 ) )
      most_common_ticks = int( 4 * midi.ticks_per_beat / note_length )
      logging.warning( "Rounding detected to longer power of 2: {q} ({nlen}th notes)".format( q=most_common_ticks, nlen=note_length ) )
      q_log2 = math.log( note_length, 2 )
   inp = input( "Input desired resolution, or hit Enter to accept default ({q}): ".format( q=most_common_ticks ) )
   if inp:
      return int( inp )
   else:
      return most_common_ticks


def prompt_for_time_slice(midi: funmid.SimplyNotes, selected_tracks: List[int]) -> (int, int):
   """
   Get desired section of song from user, default whole thing.
   """
   min_t = 2 ** 31
   max_t = 0
   for track_i, track in sorted( midi.by_track().items() ):
      if track_i not in selected_tracks:
         continue
      times = [note.t for note in track if note.is_edge()]
      min_t = min( min_t, min( times ) )
      max_t = max( max_t, max( times ) )
   min_final = min_t
   max_final = max_t
   if 'y' in input( "Input desired time slices? (y/N)" ).lower():
      print("One second = {sec}".format(sec=midi.ticks_per_beat * midi.bpm() / 60))
      inp = input( "Slice from? [default: {min}, {minclock}] ".format( min=min_t, minclock=midi.tick_to_mmss( min_t ) ) )
      if inp:
         min_final = max( min_t, int( inp ) )
      inp = input( "Slice to? [default: {max}, {maxclock}] ".format( max=max_t, maxclock=midi.tick_to_mmss( max_t ) ) )
      if inp:
         max_final = min( max_t, int( inp ) )
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
      if funmid.is_percussion( original_notes ):
         # do not adjust percussion, just do time slicing
         new_notes = [old for old in original_notes if old.what == funmid.MidiNote.NOTE_ON and time_start <= old.t <= time_end]
         final.extend( new_notes )
         continue

      # capture all note beginnings in the desired time frame
      note_values = [note.note for note in original_notes
                     if note.what == funmid.MidiNote.NOTE_ON and time_start <= note.t <= time_end
                     ]
      low, high = min( note_values ), max( note_values )
      lowest_c = int( low / 12.0 ) * 12
      base = lowest_c
      if high - base > 25:
         # possibly too wide of a range to capture melody :/
         highest_c = int( math.ceil( high / 12.0 ) ) * 12
         logging.debug( f"GUP BOH, too big range in track #{track_n} [{low}-{high}] (C range {lowest_c}-{highest_c})" )
         if highest_c - high < low - lowest_c:
            base = highest_c - 24
            logging.debug( f"Using (high C - 24) [{base}] as base instead" )
      # copy notes using adjusted base (and time slice)
      new_notes = []
      track_ticks = list()
      for old in sorted( original_notes, key=lambda n: n.t ):
         ENABLE_CHORDS = True
         if old.what == funmid.MidiNote.NOTE_ON and time_start <= old.t <= time_end and (ENABLE_CHORDS or old.t not in track_ticks):
            nv = max( 0, old.note - base )
            new = old.copy( note=nv )
            assert old.t == new.t, "bad t"
            assert old.dur == new.dur, "bad dur"
            # logging.info("Adjusting %s to new value %d -> %s", old, nv, new)
            new_notes.append( new )
            track_ticks.append( old.t )
      final.extend( new_notes )
   return midi.copy( notes=final )


def get_chord_root(notes: List[funmid.MidiNote]) -> funmid.MidiNote:
   """
   Given a chord, try to identify the root note. This is music theory and I'm scared.
   """
   notes_by_pitch = list(sorted(notes, key=lambda n: n.note))
   # first guess: lowest note
   retval = notes_by_pitch[0]
   if len(notes) < 3:
      # just use this guess
      logging.debug("Dichord? idk music theory babey im Just useing lowest note of %s" % notes_by_pitch)
      return retval

   # otherwise, try and figure out if we've got some funny inversion happening

   # each pitch value is 1 semitone
   # ACCORDING TO THIS GRAPH OF COMMON CHORDS ON WIKIPEDIA: https://en.wikipedia.org/wiki/Chord_(music)#Examples
   # third should be 3 (minor) or 4 (major) semitones away
   # fifth should be 6 (diminished), 8 (augmented), or 7 (everything else) semitones away
   # there can also be a sixth at 9 semitones, or a seventh at 10 (min) or 11 (maj)
   # note, this doesn't account for sus chords and stuff. this world is so corrupt
   left_to_guess = notes_by_pitch[:]
   while left_to_guess:
      root = left_to_guess[0]
      remainder = notes_by_pitch[:]
      remainder.remove(root)
      shifted_root = root.copy(note=root.note-12)
      third = remainder[0]
      fifth = remainder[1]
      for guess in (root, shifted_root):
         if 3 <=abs(third.note - guess.note) <= 4:
            # third appears ok
            if 6 <= abs(fifth.note - guess.note) <= 8:
               # fifth appears ok too
               logging.debug(f"Think we found a chord with root {root}: {guess}, {third}, {fifth}")
               return root

      left_to_guess.remove(root)
   logging.debug("Didn't see a chord in %s", ', '.join(str(n) for n in notes_by_pitch))
   return retval


def flatten(midi: funmid.SimplyNotes, priorities: List[int]) -> FlatNotes:
   """
   Remove chords/collisions so only one note starts at any given time.
   """
   final = { }
   for t, notes in sorted( midi.by_time().items() ):
      notes_by_prio = sorted( notes, key=lambda note: priorities.index( note.track ) )
      # if more than one "winner", we have a little extra decision making to do...

      winning_track = notes_by_prio[0].track
      winning_notes = [note for note in notes_by_prio if note.track == winning_track]
      if len(winning_notes) == 1:
         # just one note is being played now, hooray
         final[t] = winning_notes[0]
      elif funmid.is_percussion(winning_notes):
         # multiple percussion hits are happening - sort by approx. impact to rhythm
         # general order of notes in midi spec is kick, snare, hi hat, cymbal, other
         # -- seems good enough to me! lowest 'note' wins.
         final[t] = sorted(winning_notes, key=lambda note: note.note)[0]
      else:
         # we have a chord!! uh oh!!
         final[t] = get_chord_root(winning_notes)
   return final


def quantize_to_beat(notes: FlatNotes, quantize_to: int) -> funmid.Notes:
   """
   Remove notes that don't fit into the given beat (or insert rests if nothing playing on beat).
   """
   t = 0
   final = []
   last_note = funmid.MidiNote()
   len_change_stack = 1
   pool = notes.copy()
   # scroll through timeline and lay down notes on the beat
   while t < max( pool.keys() ):
      if len( final ) > MAX_NOTES:
         break
      p2 = sorted( pool.copy() )
      # cull notes that the timeline has already passed by
      for next_time in sorted( p2 ):
         n = pool[next_time]
         if n.dur > 0 and next_time + n.dur <= t:  # equal case is for notes that end at exactly t
            pool.pop( next_time )
         elif next_time > t:
            # can stop culling, we're looking at the future now
            break

      # get candidate for next note
      next_time = sorted(pool)[0]
      for candidate_t in sorted(pool):
         # get the note that starts closest to this time (without going over)
         if candidate_t > t:
            break
         elif (t - candidate_t) < (t - next_time):
            next_time = candidate_t

      next_note = pool[next_time]

      # if the current time is within the candidate note's start/end time, play it
      if next_time <= t < next_time + next_note.dur:
         # we have a note playing :)
         pass
      else:
         # nothing playing
         next_note = funmid.MidiNote()  # empty/rest
         next_note.t = t
         if last_note.is_rest():
            next_note = last_note  # reuse the rest with proper t

      if not g_ChangeLengths:
         # just in case this fires too often or something
         # TBD maybe only change lengths for priority #1 track?
         final.append(next_note)
         pool.pop(next_note.t)
         last_note = next_note
         t += quantize_to
         continue

      # is a note still playing from last tick?
      if (next_note is last_note) or (next_note.is_rest() and last_note.is_rest()):
         # increment how long this note has been playing for
         len_change_stack += 1
         pass
      else:
         if len_change_stack > 1:
            # new note after a long note
            # insert the length changes before last note, append length decs after last note
            idx = final.index(last_note) if final else 0
            stack = len_change_stack
            added = 0
            while stack > 1:
               final.insert( idx, LengthChange(t, LengthChange.INC) )
               added += 1
               stack /= 2
            idx += added
            for i in range(added):
               final.insert( idx+1, LengthChange(t, LengthChange.DEC) )
            if stack != 1:
               # there was an extra beat (e.g. dotted note) that didn't quite fit
               extra = funmid.MidiNote()
               extra.t = t
               final.append( extra )
            len_change_stack = 1
         else:
            # new note after a regular note/rest
            pass

         final.append(next_note)

      last_note = next_note
      t += quantize_to

   # did we end on a long note that we never got to finish?
   if len_change_stack > 1:
      idx = final.index(last_note)
      stack = len_change_stack
      while stack > 1:
         final.insert( idx, LengthChange(LengthChange.INC) )
         stack /= 2
      idx = final.index(last_note)
      stack = len_change_stack
      while stack > 1:
         final.insert( idx+1, LengthChange(LengthChange.DEC) )
         stack /= 2
   return final


def crunch(midi: funmid.SimplyNotes, track_priority: List[int], tick_quantize: int, time_slice: Tuple[int, int]) -> funmid.Notes:
   """
   Smush all desired tracks together into a single flat list.
   """
   scale_corrected_notes = scale( midi, track_priority, time_slice )
   flat_notes = flatten( scale_corrected_notes, track_priority )
   quant = quantize_to_beat( flat_notes, tick_quantize )

   # mix in bpm changes
   last_t = -1
   for t, bpm_change in midi.bpm_info.items():
      # look through quant for where to insert bpm change
      for note in quant[:]:
         nt = note.t
         if last_t <= t <= nt:
            idx = quant.index(note)
            quant.insert(idx, BPMChange(t, bpm_change))
            break
         last_t = nt
   return quant

use_hev = random.randint(1,100)
if use_hev < (g_GrimeFactor/2):
   print("** GRIME FACTOR ENABLED **")

def get_vox_instrument(note: funmid.MidiNote) -> str:
   """Convert a general midi patch to a vox instrument"""
   if note.is_drums():
      return '<drums>'  # will convert later, this is just for `*` detection
   patch = note.patch + 1
   if patch in (12, 15):  # vibraphone, tubular bells
      return 'bonkwarn'  # coconut bonk
   if patch in (13, 14, 116): # marimba, xylophone, woodblock
      return 'd5'  # hazymazewood
   elif patch <= 16:  # pianos n such
      return 'n5'  # yossynote
   elif patch <= 24:  # organs
      return 'n2'  # catnote
   elif patch <= 27:  # acoustic guitar
      return 'n8'  # dantnote
   elif patch == 30:  # overdriven guitar
      if use_hev < g_GrimeFactor:
         return 'hl_hev>.25'  # medium fuzz
      else:
         return 'n7'  # bupnote
   elif patch == 31:  # distortion guitar
      if use_hev < (g_GrimeFactor/2):
         return 'hl_hev>.5'  # LOUD fuzz
      else:
         return 'n4'  # dootnote
   elif patch <= 32:  # electric guitar
      return 'n4'  # dootnote
   elif patch <= 40:  # bass
      return 'n10'  # slapnote
   elif patch == 46:  # pizzicato
      return 'n17'  # pizzicatonote. wow!
   elif patch <= 47:  # string
      return 'n13'  # shynote
   elif patch == 48:  # timpani
      return 'd2'  # kick
   elif patch <= 52:  # strings
      return 'n2'  # catnote
   elif patch <= 55 or patch in (102, 103):  # choir, goblins, echoes
      return 'n16'  # cursed hauntnote
   elif patch == 56:  # orch hit
      return 'n12'  # orchnote
   elif patch == 59:  # tuba
      return 'n7'  # bupnote
   elif patch in (57, 60):  # trumpet, muted trumpet
      return 'n18'  # zunnote
   elif patch in (60, 61, 71):  # french horn, bassoon
      return 'n14'  # morshunote
   elif patch <= 72:  # brass
      return 'n1'  # cnote
   elif patch in (77, 80, 99):  # blown bottle, ocarina, crystal
      return 'n15'  # hazymazenote
   elif patch <= 80:  # winds
      return 'n11'  # jarnote
   elif patch == 81:  # lead 1 square
      return 'n9' # downote
   elif patch in (82, 86, 91, 94):  # sawtooth, voice, polysynth, metallic
      return 'n14'  # morshunote
   elif patch in (92, 101):  # choir pad, brightness
      return 'newwarn'  # nsmb ba!
   elif patch in (118, 119):  # toms etc
      return 'd2'  # kick
   elif patch in (120, 122, 123):  # reverse cymbal, breath, seashore
      return 'defeatwarn>.4'  # gated white noise
   else:
      # idk there are 11 kk notes just use those
      return 'kk%d' % (1 + int( (patch - 80) / (48 / 11) ))


def get_vox_pitch(note: int) -> str:
   """Convert a note (length ignored) to a vox string suffix"""

   scales = [
      '-10', '-9', '-9', '-8', '-7', '-7', '-6', '-5', '-4', '-3', '-2', '-', '',
      '+-', '+', '+2', '+3-', '+4-', '+5', '+6', '+7', '+8', '+9', '+10'
   ]
   if note >= len( scales ):
      scale_s = '+10'
   elif note < 0:
      scale_s = '-10'
   else:
      scale_s = scales[note]

   return scale_s


def get_vox_drums(note: int) -> str:
   """Convert a percussion note to a vox string"""
   if note in (87, 86):  # open/mute surdo
      return 'd4'
   elif note == 85:  # castanets
      return 'kk12'
   elif note == 83:  # jingle bells
      return 'shinewarn'  # lol
   if note == 79:  # low cuica
      return 'n3'
   elif note == 78:  # high cuica
      return 'n3+6'
   elif note == 77:  # low wood block
      return 'd6-4'
   elif note == 76:  # high wood block
      return 'dd-2'
   elif note == 75:  # claves
      return 'd5'
   elif note in (82, 81, 70, 69, 54, 51, 46):  # triangle, maracas, cabasa, tambourine, ride, hi hat
      return "'s"
   elif note in (80, 59, 44, 42):  # mute triangle, ride, hi hats
      return "kk14"
   elif note == 68:  # low agogo
      return 'gmod_metal-2'
   elif note == 67:  # high agogo
      return 'gmod_metal+2'
   elif note == 64:  # lo conga
      return 'd4'
   elif note in (62, 63):  # mute/open hi congas
      return 'd4+4'
   elif note == 60:  # hi bongo
      return 'd6+4'
   elif note == 61:  # lo bongo
      return 'd6'
   elif note in (57, 49):  # crash cymbals
      return 'kk14-10'
   elif note == 56:  # cowbell
      return 'bonkwarn+8'
   elif note == 55:  # splash cymbal
      return 'defeatwarn+6'
   elif note in (50, 48, 47, 45, 43, 41):  # toms
      return 'd2+%d' % (5 + (note - 40) / 2)
   elif note in (40, 38):  # snares
      return 'd1'
   elif note == 39:  # clap/scratch
      return 'd3'
   elif note == 37:  # side stick
      return 'kk12'
   elif note in (36, 35):  # bass drum
      return 'd2'
   elif note == 34:  # metronome bell
      return 'hl_crowbar'
   elif note == 33:  # metronome tick
      return 'gmod_ragdoll'  # lol
   elif note == 32:  # square click
      return 'gmod_wood'  # ehehehh
   elif note == 31:  # sticks
      return 'kk13'
   elif note == 30:  # scratch pull
      return 'smw_yossy>.5'
   elif note == 29:  # scratch push
      return 'smw_yossy<.4'
   else:
      # probably not important........
      print( "No note for percussion: %d (%s)" % (note, funmid.midi_percussion_to_str(note) ) )
      return '.'


def note_to_vox(note: funmid.MidiNote, instrument_hint: str = '') -> str:
   """Convert a note to a full vox string token (instrument[+pitch])"""
   if note.is_drums():
      return get_vox_drums( note.note )
   else:
      instrument = get_vox_instrument(note)
      if instrument_hint:
         instrument = instrument_hint
      return instrument + get_vox_pitch( note.note )


def build_voxstr(notes: funmid.Notes, note_len: int) -> str:
   s = '^s'
   lastnote = None
   cur_bpm = 0
   cur_len = note_len
   last_len = 0
   for note in notes:
      if note.what == LengthChange.INC:
         cur_len /= 2
         continue
      elif note.what == LengthChange.DEC:
         cur_len *= 2
         continue
      elif note.what == BPMChange.BPM_CHANGE:
         if note.note != cur_bpm:
            cur_bpm = note.note
            s += f' ^bpm={cur_bpm}'
         continue

      if cur_len != last_len:
         if cur_len < 1:
            s += ' ^l=1 . (oops)'  # TODO
         else:
            s += f' ^l=%d' % cur_len
         last_len = cur_len

      if note.is_rest():
         if lastnote:
            if s[-1] not in ' .':
               s += ' '
            s += '.'
         else:
            # don't add rests at start like a lot of annoying midis do >:C
            pass
      else:
         if lastnote and note_to_vox( note ) == note_to_vox( lastnote ):
            note_s = '*'
         elif lastnote and get_vox_instrument( note ) == get_vox_instrument( lastnote ):
            note_s = note_to_vox(note, instrument_hint='*')
            if note_s == '*':
               # reset to middle C needs +0
               note_s = '*+0'
         else:
            note_s = note_to_vox( note )
         if note_s:
            s += ' ' + note_s
            lastnote = note
      if len( s ) > MAX_VOXSTR_LEN:
         break
   return s


def main(filename=r"ta-poochie.mid", gofast=False):
   logging.basicConfig( level=logging.INFO )
   if filename.startswith('file://'):
      from urllib.parse import unquote, urlparse
      filename = unquote( urlparse(filename).path )
      filename = filename.lstrip('/')
   midifile = funmid.MidiFile( filename )
   midi = midifile.to_simplynotes()

   # Collect info from user
   print( filename )
   print( '=' * 40 )
   friendly_print( midi )
   if gofast:
      trax = sorted( midi.track_names.keys() )
      time_slice = (0, 2**31)
      tick_quantize = midi.ticks_per_beat / 4
   else:
      trax = prompt_for_tracks( midi )
      time_slice = prompt_for_time_slice( midi, trax )
      tick_quantize = prompt_for_resolution( scale( midi, trax, time_slice ), trax )

   # do some sanity checkin'
   min_note_length = int( 4 * (midi.ticks_per_beat / tick_quantize) )
   default_bpm = midi.bpm()
   if min_note_length > 32:
      default_bpm = int( midi.bpm() * (min_note_length / 32) )
      min_note_length = 32
      print( "Notes are too short, increasing bpm to {bpm}".format( bpm=default_bpm ) )
   if default_bpm > 480:
      tick_quantize = int( tick_quantize * (midi.bpm() / 480) )
      default_bpm = 480
      print( "BPM too high, increasing tick quantization to {q}".format( q=tick_quantize ) )

   # Param processing done, time to build voxstr
   final_notes = crunch( midi, trax, tick_quantize, time_slice )
   bpm_info = [BPMChange(t, bpm) for (t, bpm) in midifile.get_bpms().items()]
   if not bpm_info:
      bpm_info = [BPMChange(0, default_bpm)]

   # noinspection PyTypeChecker
   final_seq = [bpm_info[0]] + final_notes
   voxstr = build_voxstr( final_seq, min_note_length )

   return voxstr


if __name__ == "__main__":
   if len( sys.argv ) == 2:
      _fn = sys.argv[1]
      _gofast = True
   else:
      _fn = input( "filename pls" ).strip( '"' )
      _gofast = False
   print( main( _fn, gofast=_gofast ) )
