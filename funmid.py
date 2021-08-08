"""
it's midi parsing. 1.1 spec thx https://www.cs.cmu.edu/~music/cmsip/readings/Standard-MIDI-file-format-updated.pdf
spoocecow 2021
"""
import logging
import sys
from typing import List, Dict


class IBuf(bytes):
    """Simple buffer class that keeps an index to last read byte"""

    index = 0

    OverrunError = OverflowError

    def __init__(self, *args, **kwargs):
        bytes.__init__(self)
        self.index = 0

    def has_bytes(self) -> bool:
        """Have we read the whole buffer?"""
        return self.index < len(self)

    def remaining(self) -> int:
        """How many bytes are left?"""
        return len(self) - self.index

    def read(self) -> int:
        """
        Read a byte from the buffer, incrementing index.
        :return: next byte in buffer
        """
        if self.remaining() < 1:
            raise IBuf.OverrunError("Buffer at end")
        rv = self[self.index]
        self.index += 1
        return rv

    def peek(self) -> int:
        """
        Peek at the next byte without incrementing the index.
        :return: next byte in buffer
        """
        return self[self.index]

    def read_bytes(self, width):
        """
        Read chunk of bytes out of buffer as new IBuf.
        :param width: number of bytes to read
        :return: new IBuf of read bytes
        """
        if self.remaining() < width:
            raise IBuf.OverrunError("Buffer has {} bytes remaining, less than requested {}".format(self.remaining(), width))
        buf = [self.read() for _ in range(width)]
        return IBuf(buf)

    def read_int(self, n_bytes: int = 4) -> int:
        """
        Unpack bytes into an integer.
        :param n_bytes: number of bytes to read
        :return int: unpacked little endian integer
        """
        if self.remaining() < n_bytes:
            raise IBuf.OverrunError("Buffer has {} bytes remaining, less than requested {}".format(self.remaining(), n_bytes))
        i = 0
        for _ in range(n_bytes):
            n = self.read()
            i <<= 8
            i |= n
        return i

    def read_vlq(self) -> int:
        """
        Unpack Variable Length Quantity (MIDI spec type) into an integer.
        :return int: unpacked little endian Variable Length Quantity
        """
        b = self.read()
        res = b & ~0x80
        while b & 0x80:
            b = self.read()
            res <<= 7
            res |= (b & ~0x80)
        return res


class MidiNote:
    """
    Representation of a midi note on/off event with extra timing/patch info bolted on.
    """

    EMPTY = 0

    NOTE_OFF  = 0b1000
    NOTE_ON   = 0b1001
    KEYPRES   = 0b1010
    CONTROLCH = 0b1011
    PROGCH    = 0b1100
    KEYSLAM   = 0b1101
    PITCHWHL  = 0b1110

    def __init__(self):
        self.what = MidiNote.EMPTY
        self.channel = 0
        self.track = 0
        self.patch = 0
        self.t = 0
        self.dur = 0
        self.note = 0
        self.velocity = 0

    def __repr__(self):
        if self.is_rest():
            return '<N -- >'
        return '<N%0x t%d c%d>' % (self.what, self.t, self.channel)

    def __str__(self):
        if self.what == MidiNote.NOTE_ON:
            return 'Note<on ch:%d t:%d dur:%d p:%d n:%d v:%d>' % (self.channel, self.t, self.dur, self.patch, self.note, self.velocity)
        elif self.what == MidiNote.NOTE_OFF:
            return 'Note<off ch:%d t%d p:%d n:%d>' % (self.channel, self.t, self.patch, self.note)
        else:
            return repr(self)

    def __lt__(self, other):
        return self.t < other.t

    def is_drums(self):
        return self.channel == 9

    def is_rest(self):
        return self.what == MidiNote.EMPTY

    def is_edge(self):
        return self.what in (MidiNote.NOTE_ON, MidiNote.NOTE_OFF)

    def copy(self, **kwargs):
        """
        Return a copy of this note, with the specified changes made in the kwargs.
        :param kwargs: fields/values to override on this note
        :return: new note
        """
        other = MidiNote()
        for field, value in vars(self).items():
            setattr(other, field, value)
        assert self.what == other.what
        assert str(self) == str(other)
        for field, value in kwargs.items():
            setattr(other, field, value)
        return other


Notes = List[MidiNote]
TrackNames = Dict[int, str]
# what a revoltin' development these are vvv
TrackNotes = Dict[int, Notes]  # notes organized by MIDI track
ChanNotes = Dict[int, Notes]  # notes organized by channel
TimeNotes = Dict[int, Notes]  # notes organized by tick time. my other crap was written for this ugh.


class SimplyNotes:
    """
    Simply... Notes.
    Quick container to be fed into other stuff.
    """

    def __init__(self, notes: Notes, track_names: TrackNames, channel_names: TrackNames, bpm: int = 120, ticks_per_beat: int = 120):
        self.notes = notes
        self.track_names = track_names
        self.channel_names = channel_names
        self.bpm = bpm
        self.ticks_per_beat = ticks_per_beat

        self.__by_track = {}
        self.__by_channel = {}
        self.__by_time = {}

        self.__cleanup()

    def __cleanup(self):
        # clean up track names for presentation later
        seen_tracks = []
        for note in self.notes:
            if note.track not in seen_tracks:
                seen_tracks.append(note.track)
        for track in list(self.track_names.keys()):
            if track not in seen_tracks:
                self.track_names.pop(track)  # some tracks have just meta info, etc. don't show em.

    def by_track(self) -> TrackNotes:
        if self.__by_track:
            return self.__by_track
        res = dict()
        for note in self.notes:
            if note.track not in res:
                res[note.track] = [note]
            else:
                res[note.track].append(note)
        self.__by_track = res
        return res

    def by_channel(self) -> ChanNotes:
        if self.__by_channel:
            return self.__by_channel
        res = dict()
        for note in self.notes:
            if note.channel not in res:
                res[note.channel] = [note]
            else:
                res[note.channel].append(note)
        self.__by_channel = res
        return res

    def by_time(self) -> TimeNotes:
        if self.__by_time:
            return self.__by_time
        res = dict()
        for note in self.notes:
            if note.t not in res:
                res[note.t] = [note]
            else:
                res[note.t].append(note)
        self.__by_time = res
        return res

    def tick_to_mmss(self, tick: int) -> str:
        beats = tick / self.ticks_per_beat
        mins = int(beats // self.bpm)
        secs = int(((beats % self.bpm) / self.bpm) * 60)
        return '{:02d}:{:02d}'.format(mins, secs)

    def copy(self, **kwargs):
        """
        Return a copy of this collection, with the specified changes made in the kwargs.
        :param kwargs: fields/values to override on the new collection
        :return: new collection
        """
        other = SimplyNotes(self.notes.copy(), self.track_names, self.channel_names, self.bpm, self.ticks_per_beat)
        for field, value in kwargs.items():
            setattr(other, field, value)
        other.__cleanup()
        return other


def is_percussion(notes: Notes) -> bool:
    return all(map(MidiNote.is_drums, notes))


class MidiFile:
    """
    MIDI file parsing and convenience conversion methods.
    """
    TIME_TICKS = 0
    TIME_TIMECODE = 1

    def __init__(self, fn):
        self.filename = fn
        self._bytes = bytearray()
        with open(self.filename, 'rb') as f:
            self._bytes = IBuf( f.read() )

        self._format = 0
        self._ntrks = 0
        self.__last_chunk = b''
        self.__last_offset = 0
        self.__track_end = False
        self._division = 0
        self.ticks_per_beat = 0
        self.bpm = 120
        self._bpm_changes = dict()
        self._time_mode = MidiFile.TIME_TICKS
        self._current_track = 0
        self._current_channel = 0
        self._current_patch = 0
        self._running_status = 0
        self._t = 0
        self.duration = 0
        self.channels = dict()
        self.messages = dict()  # indexed by track#
        self.track_names = dict()
        self.channel_names = dict()

        self.parse()

    def parse(self):
        """
        Turn this file's raw bytes into MidiNotes and such.
        """
        while self._bytes.remaining() >= 8:  # chunk type/size are 4 bytes each; some files have extra padding on end...??
            self._read_chunk()
        assert self._ntrks == self._current_track, "Wah %d != %d" % (self._ntrks, self._current_track)
        # sort channel msg lists by time, just in case channels were spread across tracks
        # don't know the midi spec itself well enough to know if this is allowed justt lookin at file specc haheheh
        for ch in self.channels:
            msgs = self.channels[ch]
            self.channels[ch] = list(sorted(msgs, key=lambda m: m.t))

    def get_notes(self) -> Notes:
        """
        Unpack all notes into just Note On/Off actions, sorted by absolute time within the midi (no deltas)
        :return Notes: list of notes sorted by absolute midi time
        """
        flattened = []
        for c in self.channels:
            on_notes = []
            for msg in self.channels[c]:
                assert isinstance(msg, MidiNote)
                if not msg.is_edge():
                    continue

                if msg.what == MidiNote.NOTE_ON:
                    on_notes.append(msg)
                elif msg.what == MidiNote.NOTE_OFF:
                    for on_note in on_notes:
                        if on_note.patch == msg.patch and on_note.note == msg.note:
                            # this note is now done
                            on_note.dur = msg.t - on_note.t
                            on_notes.remove(on_note)
                            break

                flattened.append(msg)

            if len(on_notes) != 0:
                logging.warning("ended with some notes that never turned off...? %s", on_notes)
                for note in on_notes:
                    note.dur = self.duration - note.t

        return list(sorted(flattened, key=lambda n: n.t))

    def to_simplynotes(self) -> SimplyNotes:
        """
        Convert read data into SimplyNotes container.
        :return SimplyNotes: simply... the notes. and other things
        """
        return SimplyNotes(
            notes=self.get_notes(),
            track_names=self.track_names.copy(),
            channel_names=self.channel_names.copy(),
            bpm=self.bpm,
            ticks_per_beat=self.ticks_per_beat
        )

    def _read_chunk(self):
        chunk_type = self._bytes.read_bytes(4)
        chunk_length = self._bytes.read_int(4)
        chunk = self._bytes.read_bytes(chunk_length)
        self._process_chunk(chunk_type, chunk)
        self.__last_chunk = chunk
        self.__last_offset += 8 + len(chunk)
        return chunk

    def _process_chunk(self, chunk_type: bytes, chunk_data: IBuf):
        if chunk_type == b'MThd':
            return self._process_header(chunk_data)
        elif chunk_type != b'MTrk':
            logging.warning("Ignoring alien chunk type: %r", chunk_type)
            return

        self._t = 0  # reset time for each track
        self._running_status = 0
        self.__track_end = False
        while chunk_data.has_bytes():
            delta_time = chunk_data.read_vlq()
            self._t += delta_time
            event_1st_byte = chunk_data.peek()
            if event_1st_byte == 0xF0 or event_1st_byte == 0xF7:
                # sysex event, don't care, skip past
                chunk_data.read()  # throw away peeked byte
                event_len = chunk_data.read_vlq()
                logging.debug("skipping %d bytes of sysex data" % event_len)
                sysex_data = chunk_data.read_bytes(event_len)  # throw away sysex event
                if sysex_data[-1] != 0xF7:
                    logging.error("against spec or I f'ed up: sysex data doesn't end with 0xf7")
            elif event_1st_byte == 0xFF:
                # meta event
                self._process_meta_event(chunk_data)
            else:
                # MIDI event yaaaayyy
                self._process_midi_event(delta_time, chunk_data)
        assert self.__track_end, "Didn't see track end"
        self.duration = max(self.duration, self._t)
        self._current_track += 1

    def _process_header(self, chunk_data: IBuf):
        assert(len(chunk_data) == 6)
        self._format = chunk_data.read_int(2)
        self._ntrks = chunk_data.read_int(2)
        if self._format == 0:
            # single track format should only have one track
            assert self._ntrks == 1, "Format 0 MIDI must have only 1 track, not %d" % self._ntrks
        elif self._format == 2:
            # all tracks have separate tempos o_O complciatuiated!!!! wHAwawAwaw
            logging.warning("Format 2 midi woioioi")
        self.track_names = {n: '' for n in range(self._ntrks)}
        self._division = chunk_data.read_int(2)

        """
        Spec 1.0 pg 4:
        The third word, <division>, specifies the meaning of the delta-times. It has two formats,
        one for metrical time, and one for time-code-based time: [snip]
        
        If bit 15 of <division> is a zero, the bits 14 thru 0 represent the number of delta-time "ticks"
        which make up a quarter-note. For instance, if <division> is 96, then a time interval of an
        eighth-note between two events in the file would be 48.
        If bit 15 of <division> is a one, delta-times in a file correspond to subdivisions of a second, in
        a way consistent with SMPTE and MIDI time code. Bits 14 thru 8 contain one of the four
        values -24, -25, -29, or -30, corresponding to the four standard SMPTE and MIDI time code
        formats (-29 corresponds to 30 drop frame), and represents the number of frames per second.
        These negative numbers are stored in two's complement form. The second byte (stored
        positive) is the resolution within a frame: typical values may be 4 (MIDI time code resolution),
        8, 10, 80 (bit resolution), or 100. This system allows exact specification of time-code-based
        tracks, but also allows millisecond-based tracks by specifying 25 frames/sec and a resolution of
        40 units per frame. If the events in a file are stored with bit resolution of thirty-frame time
        code, the division word would be E250 hex.
        """

        if self._division & 0x8000 == 0x8000:
            # fps = bits 14-8, stored as negative number (2s compl.)
            # use ^ instead of ~ to subvert python helpful auto-negation
            frames_per_second = int(((self._division >> 8) ^ 0x7F) + 1)
            assert frames_per_second in (-24, -25, -29, -30), "Unexpected negative SMPTE format"
            ticks_per_frame = int(self._division & 0xFF)
            logging.debug("fps:%d tpf:%d  division:%0x", frames_per_second, ticks_per_frame, self._division)
            self.ticks_per_beat = ticks_per_frame/frames_per_second  # iono todo
        else:
            self.ticks_per_beat = int(self._division)

    def _process_meta_event(self, chunk_data: IBuf):
        assert chunk_data.read() == 0xFF, "No meta FF byte"
        meta_type = chunk_data.read()
        meta_len = chunk_data.read_vlq()
        meta_data = chunk_data.read_bytes(meta_len)
        if meta_type == 0x00:
            # sequence number
            assert meta_len == 2
            seq = meta_data.read_int(2)
            logging.info("Sequence: %d", seq)
        elif meta_type in (0x01, 0x02):
            # Text Event, Copyright Notice
            # don't care, pass over
            logging.debug("Generic text: %s", ''.join(chr(c) for c in meta_data))
        elif meta_type == 0x03:
            # sequence/track name - this might be good to save
            seq_name = ''.join(chr(c) for c in meta_data)
            self.track_names[self._current_track] = seq_name
            logging.info("Track %d sequence name: %s", self._current_track, seq_name)
        elif meta_type == 0x04:
            # instrument name - might also be good to save
            instr_name = ''.join(chr(c) for c in meta_data)
            if not self.track_names.get(self._current_track):
                self.track_names[self._current_track] = instr_name
            if not self.channel_names.get(self._current_channel):
                self.channel_names[self._current_channel] = instr_name
                logging.debug("Channel %d instrument name: %s", self._current_channel, instr_name)
            logging.info("Track %d instrument name: %s", self._current_track, instr_name)
        elif meta_type <= 0x0F:
            # text event - lyric, marker, cue point, program name, device name
            # just flavor text, don't care
            logging.debug("Test event %d: %s", meta_type, ''.join(chr(c) for c in meta_data))
        elif meta_type == 0x20:
            # channel prefix
            assert meta_len == 1
            self._current_channel = meta_data.read()
            logging.info("Current effective channel: %d", self._current_channel)
        elif meta_type == 0x21:
            # port
            assert meta_len == 1
            logging.debug("Midi port: %d", meta_data.read())
        elif meta_type == 0x2F:
            # end of track
            assert meta_len == 0
            assert self.__track_end == False, "Already seen end of track"
            self.__track_end = True
            if chunk_data.remaining():
                logging.error("Data still remaining (%d B) in track after seeing track end", chunk_data.remaining())
            logging.info("End of track %d", self._current_track)
        elif meta_type == 0x51:
            # tempo change
            assert meta_len == 3
            # represented in microseconds per MIDI quarter-note
            # (aka 24ths of a microsecond per MIDI clock)
            us_per_midi_qtr_note = meta_data.read_int(3)
            self.bpm = int(60 * (1e6 / us_per_midi_qtr_note))
            self._bpm_changes[self._t] = self.bpm
            logging.info("Tempo change: %d us / qtr note = %d bpm", us_per_midi_qtr_note, self.bpm)
        elif meta_type == 0x54:
            # SMPTE offset
            assert meta_len == 5
            # don't care
            logging.debug("SMPTE offset ahuhfbfuh")
        elif meta_type == 0x58:
            # time signature
            assert meta_len == 4
            num = meta_data.read()
            denom = 2 ** meta_data.read()
            midi_clocks_per_metronome_click = meta_data.read()
            notated_32nd_notes_per_midi_qtr_note = meta_data.read()
            logging.info("%d/%d time signature", num, denom)
        elif meta_type == 0x59:
            # key signature
            assert meta_len == 2
            sf = meta_data.read()  # <0 flats, 0=C, >0 sharps
            mi = meta_data.read()  # 0 major, 1 minor
            logging.debug("key signature %d %d", sf, mi)
        elif meta_type == 0x7F:
            # sequence specific meta-event
            pass
        else:
            logging.warning("unknown meta: type:%x len:%d", meta_type, meta_len)

    def _process_midi_event(self, delta_time: int, event_data: IBuf):
        status = event_data.peek()
        if status & 0x80 == 0:
            # continuation of previous status
            assert self._running_status != 0, "Continued status, but nothing set in this chunk"
            status = self._running_status
        else:
            status = event_data.read()
            self._running_status = status
        code = (status & 0xF0) >> 4
        assert code & 0x8 == 0x8, "Bad status: %0x" % status
        channel = status & 0x0F
        self._current_channel = channel

        msg = MidiNote()
        msg.what = code
        msg.channel = channel
        msg.t = self._t
        msg.track = self._current_track
        msg.patch = self._current_patch

        if code == MidiNote.NOTE_OFF:
            # note off
            msg.note = event_data.read()
            msg.velocity = event_data.read()
        elif code == MidiNote.NOTE_ON:
            # note on
            msg.note = event_data.read()
            msg.velocity = event_data.read()
            if msg.velocity == 0:
                msg.what = MidiNote.NOTE_OFF  # lie, but makes reprs more readable
        elif code == MidiNote.KEYPRES:
            # Polyphonic Key Pressure (Aftertouch) (??)
            key = event_data.read()
            velocity = event_data.read()
            return  # don't add message
        elif code == MidiNote.CONTROLCH:
            # Control Change
            controller = event_data.read()
            value = event_data.read()
            return  # don't add message
        elif code == MidiNote.PROGCH:
            # Program Change
            self._current_patch = event_data.read()
            return  # don't add message
        elif code == MidiNote.KEYSLAM:
            # Channel Pressure (After-touch) (?????????)
            velocity = event_data.read()
            return  # don't add message
        elif code == MidiNote.PITCHWHL:
            # Pitch Wheel Change
            lsb = event_data.read()
            msb = event_data.read()
            return  # don't add message
        elif code == 0b1111:
            # System Common Messages, we don't care about this
            if channel == 0:
                # sysex dump, have to read until we see magic byte 0b11110111
                while event_data.read() != 0b11110111:
                    pass
            elif channel == 0b0010:
                # Song Position Pointer
                lsb = event_data.read()
                msb = event_data.read()
            elif channel == 0b0011:
                # Song Select
                s = event_data.read()
            # all other System Common / Real-Time Messages do not have associated data (yay)
            return  # don't add message

        if self._current_track not in self.messages:
            self.messages[self._current_track] = []
        if channel not in self.channels:
            self.channels[channel] = []
        self.messages[self._current_track].append( msg )
        self.channels[channel].append( msg )


def midi_instrument_to_str(patch: int) -> str:
    # from https://www.cs.cmu.edu/~music/cmsip/readings/GMSpecs_Patches.htm
    return {
        1: "Acoustic Grand Piano",
        2: "Bright Acoustic Piano",
        3: "Electric Grand Piano",
        4: "Honky-Tonk Piano",
        5: "Electric Piano 1",
        6: "Electric Piano 2",
        7: "Harpsichord",
        8: "Clavinet",
        9: "Celesta",
        10: "Glockenspiel",
        11: "Music Box",
        12: "Vibraphone",
        13: "Marimba",
        14: "Xylophone",
        15: "Tubular Bells",
        16: "Dulcimer",
        17: "Drawbar Organ",
        18: "Percussive Organ",
        19: "Rock Organ",
        20: "Church Organ",
        21: "Reed Organ",
        22: "Accoridon",
        23: "Harmonica",
        24: "Tango Accordion",
        25: "Acoustic Guitar (nylon)",
        26: "Acoustic Guitar (steel)",
        27: "Electric Guitar (jazz)",
        28: "Electric Guitar (clean)",
        29: "Electric Guitar (muted)",
        30: "Overdriven Guitar",
        31: "Distortion Guitar",
        32: "Guitar Harmonics",
        33: "Acoustic Bass",
        34: "Electric Bass (finger)",
        35: "Electric Bass (pick)",
        36: "Fretless Bass",
        37: "Slap Bass 1",
        38: "Slap Bass 2",
        39: "Synth Bass 1",
        40: "Synth Bass 2",
        41: "Violin",
        42: "Viola",
        43: "Cello",
        44: "Contrabass",
        45: "Tremolo Strings",
        46: "Pizzicato Strings",
        47: "Orchestral Harp",
        48: "Timpani",
        49: "String Ensemble 1",
        50: "String Ensemble 2",
        51: "SynthStrings 1",
        52: "SynthStrings 2",
        53: "Choir Aahs",
        54: "Voice Oohs",
        55: "Synth Voice",
        56: "Orchestra Hit",
        57: "Trumpet",
        58: "Trombone",
        59: "Tuba",
        60: "Muted Trumpet",
        61: "French Horn",
        62: "Brass Section",
        63: "SynthBrass 1",
        64: "SynthBrass 2",
        65: "Soprano Sax",
        66: "Alto Sax",
        67: "Tenor Sax",
        68: "Baritone Sax",
        69: "Oboe",
        70: "English Horn",
        71: "Bassoon",
        72: "Clarinet",
        73: "Piccolo",
        74: "Flute",
        75: "Recorder",
        76: "Pan Flute",
        77: "Blown Bottle",
        78: "Shakuhachi",
        79: "Whistle",
        80: "Ocarina",
        81: "Lead 1 (square)",
        82: "Lead 2 (sawtooth)",
        83: "Lead 3 (calliope)",
        84: "Lead 4 (chiff)",
        85: "Lead 5 (charang)",
        86: "Lead 6 (voice)",
        87: "Lead 7 (fifths)",
        88: "Lead 8 (bass+lead)",
        89: "Pad 1 (new age)",
        90: "Pad 2 (warm)",
        91: "Pad 3 (polysynth)",
        92: "Pad 4 (choir)",
        93: "Pad 5 (bowed)",
        94: "Pad 6 (metallic)",
        95: "Pad 7 (halo)",
        96: "Pad 8 (sweep)",
        97: "FX 1 (rain)",
        98: "FX 2 (soundtrack)",
        99: "FX 3 (crystal)",
        100: "FX 4 (atmosphere)",
        101: "FX 5 (brightness)",
        102: "FX 6 (goblins)",
        103: "FX 7 (echoes)",
        104: "FX 8 (sci-fi)",
        105: "Sitar",
        106: "Banjo",
        107: "Shamisen",
        108: "Koto",
        109: "Kalimba",
        110: "Bagpipe",
        111: "Fiddle",
        112: "Shanai",
        113: "Tinkle Bell",
        114: "Agogo",
        115: "Steel Drums",
        116: "Woodblock",
        117: "Taiko Drum",
        118: "Melodic Tom",
        119: "Synth Drum",
        120: "Reverse Cymbal",
        121: "Guitar Fret Noise",
        122: "Breath Noise",
        123: "Seashore",
        124: "Bird Tweet",
        125: "Telephone Ring",
        126: "Helicopter",
        127: "Applause",
        128: "Gunshot",
    }.get(patch + 1, "?? %d ??" % patch)


def midi_percussion_to_str(note: int) -> str:
    # from http://www.music.mcgill.ca/~ich/classes/mumt306/StandardMIDIfileformat.html
    return {
        35: "Acoustic Bass Drum",
        36: "Bass Drum 1",
        37: "Side Stick",
        38: "Acoustic Snare",
        39: "Hand Clap",
        40: "Electric Snare",
        41: "Low Floor Tom",
        42: "Closed Hi Hat",
        43: "High Floor Tom",
        44: "Pedal Hi-Hat",
        45: "Low Tom",
        46: "Open Hi-Hat",
        47: "Low-Mid Tom",
        48: "Hi Mid Tom",
        49: "Crash Cymbal 1",
        50: "High Tom",
        51: "Ride Cymbal 1",
        52: "Chinese Cymbal",
        53: "Ride Bell",
        54: "Tambourine",
        55: "Splash Cymbal",
        56: "Cowbell",
        57: "Crash Cymbal 2",
        58: "Vibraslap",
        59: "Ride Cymbal 2",
        60: "Hi Bongo",
        61: "Low Bongo",
        62: "Mute Hi Conga",
        63: "Open Hi Conga",
        64: "Low Conga",
        65: "High Timbale",
        66: "Low Timbale",
        67: "High Agogo",
        68: "Low Agogo",
        69: "Cabasa",
        70: "Maracas",
        71: "Short Whistle",
        72: "Long Whistle",
        73: "Short Guiro",
        74: "Long Guiro",
        75: "Claves",
        76: "Hi Wood Block",
        77: "Low Wood Block",
        78: "Mute Cuica",
        79: "Open Cuica",
        80: "Mute Triangle",
        81: "Open Triangle",
    }.get(note, "?? %d ??" % note)


if __name__ == "__main__":
    _f = MidiFile(sys.argv[2])
    _f.parse()
    _notes = _f.to_simplynotes()
