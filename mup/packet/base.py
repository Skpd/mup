import struct

C1, C2, C3, C4 = 0xC1, 0xC2, 0xC3, 0xC4


class Base(bytearray):
    def is_double(self):
        return self[0] in {0xC2, 0xC4}

    @property
    def head(self):
        return self[3] if self.is_double() else self[2]

    @head.setter
    def head(self, value):
        p = 3 if self.is_double() else 2
        self[p] = value

    @property
    def sub(self):
        return self[4] if self.is_double() else self[3]

    @sub.setter
    def sub(self, value):
        p = 4 if self.is_double() else 3
        self[p] = value

    @property
    def length(self):
        if self.is_double():
            return self[1] << 8 | self[2]
        else:
            return self[1]

    @length.setter
    def length(self, length):
        if self.is_double():
            self[1] = length >> 8 & 0xFF
            self[2] = length & 0xFF
        else:
            self[1] = length & 0xFF

    @property
    def key(self):
        if self.is_double():
            return self[3], self[4]
        else:
            return self[2], self[3]


# field types: size in bytes (None: up to the end of the packet), pack(value) -> bytes, unpack(bytes) -> value

class Int:
    """Integer in a struct format, the format carries the byte order: '<H' little endian, '>H' big endian."""

    def __init__(self, fmt):
        self.struct = struct.Struct(fmt)
        self.size = self.struct.size

    def pack(self, value):
        return self.struct.pack(value)

    def unpack(self, data):
        return self.struct.unpack(data)[0]


class Cid(Int):
    """Object id: 2 bytes big endian. The high bit is a flag, masked off when reading."""

    def __init__(self):
        super().__init__('>H')

    def unpack(self, data):
        return super().unpack(data) & 0x7FFF


class Str:
    """Fixed size latin-1 string, zero padded: names, account, ip."""

    def __init__(self, size):
        self.size = size

    def pack(self, value):
        data = value.encode('latin-1')
        if len(data) > self.size:
            raise ValueError('{!r} is longer than {} bytes'.format(value, self.size))
        return data.ljust(self.size, b'\0')

    def unpack(self, data):
        return bytes(data).split(b'\0', 1)[0].decode('latin-1')


class Raw:
    """Fixed size bytes: equipment, version, serial."""

    def __init__(self, size):
        self.size = size

    def pack(self, value):
        if len(value) != self.size:
            raise ValueError('{!r} is not {} bytes'.format(value, self.size))
        return bytes(value)

    def unpack(self, data):
        return bytes(data)


class Tail:
    """Bytes up to the end of the packet: walk path. Only as the last field of a packet without a fixed size."""
    size = None

    def pack(self, value):
        return bytes(value)

    def unpack(self, data):
        return bytes(data)


class Text(Tail):
    """Zero terminated latin-1 string up to the end of the packet: chat, notice."""

    def pack(self, value):
        return value.encode('latin-1') + b'\0'

    def unpack(self, data):
        return bytes(data).split(b'\0', 1)[0].decode('latin-1')


u8 = Int('<B')
u16 = Int('<H')
u32 = Int('<I')
u16be = Int('>H')
cid = Cid()
str10 = Str(10)


class Fields:
    """
    (offset, name, type) or (offset, name, type, default) tuples. Checked when declared: in offset order, no overlaps,
    after the header, inside the size, a variable size field only at the end.
    """

    def __init__(self, owner, fields, start, size, reserved=()):
        self.fields = [f[:3] for f in fields]
        self.defaults = {f[1]: f[3] for f in fields if len(f) > 3}
        self.names = [name for _, name, _ in self.fields]
        self.variable = False
        self.end = start  # end of the fixed size part

        for n, (offset, name, kind) in enumerate(self.fields):
            if name in reserved or self.names.count(name) > 1:
                raise TypeError('{}: field name {!r} is taken'.format(owner, name))
            if offset < self.end:
                raise TypeError('{}: {} at {} overlaps what ends at {}'.format(owner, name, offset, self.end))
            if kind.size is None:
                if n != len(self.fields) - 1 or size is not None:
                    raise TypeError('{}: {} has no size, it must be the last field and the packet has no size'.format(
                        owner, name))
                self.variable = True
                self.end = offset
            else:
                self.end = offset + kind.size

        if size is not None and self.end > size:
            raise TypeError('{}: fields end at {}, after the size {}'.format(owner, self.end, size))

    def pack_into(self, owner, buf, values):
        """Writes values into buf. Returns the packed variable size field (b'' if there is none) and the values with
        the defaults filled in."""
        values = {**self.defaults, **values}
        missing = [name for name in self.names if name not in values]
        unknown = [name for name in values if name not in self.names]
        if missing or unknown:
            raise TypeError('{}: missing {}, unknown {}'.format(owner, missing, unknown))

        tail = b''
        for offset, name, kind in self.fields:
            data = kind.pack(values[name])
            if kind.size is None:
                tail = data
            else:
                buf[offset:offset + kind.size] = data
        return tail, values

    def unpack(self, owner, data):
        if len(data) < self.end:
            raise ValueError('{}: {} bytes, needs {}'.format(owner, len(data), self.end))

        return {
            name: kind.unpack(data[offset:] if kind.size is None else data[offset:offset + kind.size])
            for offset, name, kind in self.fields
        }


class Entry:
    """List at the end of a packet: count is (offset, type) of the entry count, the entries follow it, or start at
    start when fields come between."""

    def __init__(self, count, size, fields, start=None):
        self.count_offset, self.count_type = count
        self.count_end = self.count_offset + self.count_type.size
        self.start = self.count_end if start is None else start
        if self.start < self.count_end:
            raise TypeError('entry: the entries start before the count ends')
        self.size = size
        self.fields = Fields('entry', fields, 0, size)

    def pack(self, values):
        buf = bytearray(self.size)
        self.fields.pack_into('entry', buf, values)
        return buf

    def unpack(self, data):
        n = self.count_type.unpack(data[self.count_offset:self.count_end])
        if len(data) < self.start + n * self.size:
            raise ValueError('{} entries of {} bytes don\'t fit in {} bytes'.format(n, self.size, len(data)))

        return [
            self.fields.unpack('entry', data[self.start + i * self.size:self.start + (i + 1) * self.size])
            for i in range(n)
        ]


class Packet(Base):
    """
    A packet declared by its fields, offsets as in docs/protocol-097.md. Subclasses set
      code: (C1..C4, head) or (C1..C4, head, sub)
      size: total size of a fixed size packet. None for packets ending in a list or a Tail / Text field
      fields: (offset, name, type) or (offset, name, type, default). Bytes no field covers are sent as 0
      entry: Entry, for packets ending in a list
    Packet(name=value, ..., entries=[{...}, ...]) builds a packet to send.
    Packet(data) parses a received one, fields become attributes and the list goes to .entries.
    """
    code = ()
    size = None
    fields = ()
    entry = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        name = cls.__name__
        header = (3 if cls.code[0] in (C2, C4) else 2) + len(cls.code) - 1
        # fields become instance attributes, they must not shadow methods, properties or constants
        cls._fields = Fields(name, cls.fields, header, cls.size, reserved=set(dir(cls)) | {'entries'})

        if cls.entry is not None:
            if cls.size is not None or cls._fields.variable:
                raise TypeError('{}: a packet with entries has no size and no variable size field'.format(name))
            e = cls.entry
            if any(offset < e.count_end and e.count_offset < offset + kind.size
                   for offset, _, kind in cls._fields.fields) or cls._fields.end > e.start:
                raise TypeError('{}: the entry count overlaps the fields or they run into the entries'.format(name))
        elif cls.size is None and not cls._fields.variable:
            raise TypeError('{}: a fixed size packet needs a size'.format(name))

    def __init__(self, data=None, /, entries=None, **values):
        if data is not None:
            if not isinstance(data, (bytes, bytearray)) or values or entries is not None:
                raise TypeError('{}: data must be the bytes of a received packet, build with keywords'.format(
                    type(self).__name__))
            super().__init__(data)
            self.__dict__.update(self._fields.unpack(type(self).__name__, self))
            if self.entry is not None:
                self.entries = self.entry.unpack(self)
            return

        if self.entry is None:
            fixed = self.size or self._fields.end
        else:
            fixed = self.entry.start
        buf = bytearray(fixed)
        buf[0] = self.code[0]
        head = 3 if self.code[0] in (C2, C4) else 2
        buf[head:head + len(self.code) - 1] = bytes(self.code[1:])

        tail, values = self._fields.pack_into(type(self).__name__, buf, values)
        if self.entry is not None:
            entries = list(entries or ())
            buf[self.entry.count_offset:self.entry.count_end] = self.entry.count_type.pack(len(entries))
            for e in entries:
                buf += self.entry.pack(e)
            self.entries = entries
        elif entries is not None:
            raise TypeError('{} has no entries'.format(type(self).__name__))
        buf += tail

        if len(buf) > (0xFFFF if self.code[0] in (C2, C4) else 0xFF):
            raise ValueError('{}: {} bytes don\'t fit the header'.format(type(self).__name__, len(buf)))

        super().__init__(buf)
        self.length = len(self)
        self.__dict__.update(values)

    @property
    def key(self):
        return self.code[1], self.code[2] if len(self.code) > 2 else None
