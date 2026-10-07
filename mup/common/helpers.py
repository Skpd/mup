def c3hash(a, b, c):
    return a << 16 | b << 8 | c


def b2short(hi, low):
    return hi << 8 | low


def short2b(short, little_endian=True):
    if little_endian:
        return (short >> 8) & 0xff, short & 0xff
    else:
        return short & 0xff, (short >> 8) & 0xff


def str2b(s, size=10):
    """Fixed size zero padded string field, like names and account ids."""
    return bytearray(s.encode('latin-1')[:size]).ljust(size, b'\0')
