"""
it's midi parsing. 1.1 spec thx https://www.cs.cmu.edu/~music/cmsip/readings/Standard-MIDI-file-format-updated.pdf
spoocecow 2021
"""
from typing import List, Dict

class IBuf(bytes):
    """Simple buffer class that keeps an index to last read byte"""

    index = 0

    def __init__(self, *args, **kwargs):
        bytes.__init__(self)
        self.index = 0

    def has_bytes(self) -> bool:
        """Have we read the whole buffer?"""
        return self.index < len(self)

    def read(self) -> int:
        """
        Read a byte from the buffer, incrementing index.
        :return: next byte in buffer
        """
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
        buf = [self.read() for _ in range(width)]
        return IBuf(buf)

    def read_int(self, n_bytes:int=4) -> int:
        """
        Unpack bytes into an integer.
        :param n_bytes: number of bytes to read
        :return int: unpacked little endian integer
        """
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

    NOTE_OFF = 0b1000
    NOTE_ON  = 0b1001
    KEYPRES  = 0b1010
    CONTROLCH= 0b1011
    PROGCH   = 0b1100
    KEYSLAM  = 0b1101
    PITCHWHL = 0b1110

    def __init__(self):
        self.what = 0
        self.channel = 0
        self.track = 0
        self.patch = 0
        self.t = 0
        self.dur = 0
        self.note = 0
        self.velocity = 0

    def __repr__(self):
        return '<N%0x t%d c%d>' % (self.what, self.t, self.channel)

    def __str__(self):
        if self.what == MidiNote.NOTE_ON:
            return 'Note<on ch:%d t:%d dur:%d n:%d v:%d>' % (self.channel, self.t, self.dur, self.note, self.velocity)
        elif self.what == MidiNote.NOTE_OFF:
            return 'Note<off ch:%d t%d n:%d>' % (self.channel, self.t, self.note)
        else:
            return repr(self)

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

    def __init__(self, notes: Notes, track_names: TrackNames, bpm:int=120, ticks_per_beat:int=120):
        self.notes = notes
        self.track_names = track_names
        self.bpm = bpm
        self.ticks_per_beat = ticks_per_beat

        # clean up track names for presentation later
        seen_tracks = []
        for note in self.notes:
            if note.track not in seen_tracks:
                seen_tracks.append(note.track)
        for track in list(self.track_names.keys()):
            if track not in seen_tracks:
                self.track_names.pop(track)  # some tracks have just meta info, etc. don't show em.


class MidiFile:
    """
    MIDI file parsing and convenience conversion methods.
    """

    def __init__(self, fn):
        self.filename = fn
        self._bytes = bytearray()
        with open(self.filename, 'rb') as f:
            self._bytes = IBuf( f.read() )

        self._format = 0
        self._ntrks = 0
        self._division = 0
        self.ticks_per_beat = 0
        self.bpm = 0
        self._current_track = 0
        self._current_patch = 0
        self._t = 0
        self.duration = 0
        self.channels = dict()
        self.messages = dict()
        self.track_names = dict()

    def parse(self):
        """
        Turn this file's raw bytes into MidiNotes and such.
        """
        while self._bytes.has_bytes():
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
            last_msg = None
            for msg in self.channels[c]:
                if msg.what not in (MidiNote.NOTE_ON, MidiNote.NOTE_OFF):
                    continue
                if msg.what == MidiNote.NOTE_OFF and last_msg and last_msg.what == MidiNote.NOTE_ON:
                    # todo this won't represent note fadeouts correctly I don't think. not sure what to do there
                    last_msg.dur = msg.t - last_msg.t
                flattened.append(msg)
                last_msg = msg
            # make sure the last note in the channel has duration too
            if last_msg and last_msg.dur == 0:
                last_msg.dur = self.duration - last_msg.t
        return list(sorted(flattened, key=lambda n: n.t))

    def to_simplynotes(self) -> SimplyNotes:
        """
        Convert read data into SimplyNotes container.
        :return SimplyNotes: simply... the notes. and other things
        """
        return SimplyNotes(
            notes=self.get_notes(),
            track_names=self.track_names.copy(),
            bpm=self.bpm,
            ticks_per_beat=self.ticks_per_beat
        )

    def _read_chunk(self):
        chunk_type = self._bytes.read_bytes(4)
        chunk_length = self._bytes.read_int(4)
        chunk = self._bytes.read_bytes(chunk_length)
        self._process_chunk(chunk_type, chunk)

    def _process_chunk(self, chunk_type: bytes, chunk_data: IBuf):
        if chunk_type == b'MThd':
            return self._process_header(chunk_data)

        self._t = 0  # reset time for each track
        while chunk_data.index < len(chunk_data):
            delta_time = chunk_data.read_vlq()
            self._t += delta_time
            event_1st_byte = chunk_data.peek()
            if event_1st_byte == 0xF0 or event_1st_byte == 0xF7:
                # sysex event, don't care, skip past
                chunk_data.read()  # throw away peeked byte
                event_len = chunk_data.read_vlq()
                sysex_data = chunk_data.read_bytes(event_len)  # throw away sysex event
                if sysex_data[-1] != 0xF7:
                    print("against spec or I f'ed up: sysex data doesn't end with 0xf7")
            elif event_1st_byte == 0xFF:
                # meta event
                self._process_meta_event(chunk_data)
            else:
                # MIDI event yaaaayyy
                self._process_midi_event(delta_time, chunk_data)
        self.duration = max(self.duration, self._t)
        self._current_track += 1

    def _process_header(self, chunk_data: IBuf):
        assert(len(chunk_data) == 6)
        self._format = chunk_data.read_int(2)
        self._ntrks = chunk_data.read_int(2)
        if self._format == 0:
            # single track format should only have one track
            assert self._ntrks == 1
        self._division = chunk_data.read_int(2)
        if self._division & 0x8000 == 0x8000:
            # fps = bits 14-8, stored as negative number (2s compl.)
            frames_per_second = int(~(((self._division & ~0x8000) >> 8) - 1))
            ticks_per_frame = int(self._division & 0xFF)
            print("fps:%d tpf:%d  division:%0x" % (frames_per_second, ticks_per_frame, self._division))
            self.ticks_per_beat = ticks_per_frame/frames_per_second  # iono todo
        else:
            self.ticks_per_beat = int(self._division)

    def _process_meta_event(self, chunk_data: IBuf):
        assert chunk_data.read() == 0xFF, "No meta FF byte"
        meta_type = chunk_data.read()
        meta_len = chunk_data.read_vlq()
        meta_data = chunk_data.read_bytes(meta_len)
        if meta_type == 0x2F:
            # end of track
            print("End of track", self._current_track)
        elif meta_type == 0x03:
            # sequence/track name - this might be good to save
            seq_name = ''.join(chr(c) for c in meta_data)
            self.track_names[self._current_track] = seq_name
            print("Track %d sequence name: %s" % (self._current_track, seq_name))
        elif meta_type == 0x04:
            # instrument name - might also be good to save
            instr_name = ''.join(chr(c) for c in meta_data)
            if not self.track_names[self._current_track]:
                self.track_names[self._current_track] = instr_name
            print("Track %d instrument name: %s" % (self._current_track, instr_name))

    def _process_midi_event(self, delta_time:int, event_data: IBuf):
        status = event_data.read()
        code = (status & 0xF0) >> 4
        channel = status & 0x0F
        #print("track:%d stat:%0x code:%0x chan:%d" % (self._current_track, status, code, channel))
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

