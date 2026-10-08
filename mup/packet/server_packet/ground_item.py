from mup.packet.base import Packet, Entry, C2, Raw, u8, u16be

DROPPED = 0x8000  # id flag: just dropped, the client lets it fall with a sound


class GroundItems(Packet):
    """C2 20: items on the ground in view. Zen has a longer entry, it goes in GroundZen."""
    code = C2, 0x20
    entry = Entry(count=(4, u8), size=8, fields=(
        (0, 'id', u16be),  # 0..999, | DROPPED
        (2, 'x', u8),
        (3, 'y', u8),
        (4, 'item', Raw(4)),
    ))

    @classmethod
    def of(cls, ground_items, dropped=False):
        flag = DROPPED if dropped else 0
        return cls(entries=[{'id': g.id | flag, 'x': g.x, 'y': g.y, 'item': g.item.encode()} for g in ground_items])


class GroundZen(Packet):
    """C2 20: zen on the ground in view, 9 bytes each: the amount is 24 bits around the zen type's item bytes."""
    code = C2, 0x20
    entry = Entry(count=(4, u8), size=9, fields=(
        (0, 'id', u16be),
        (2, 'x', u8),
        (3, 'y', u8),
        (4, 'type', u8, 0xCF),  # zen 14/15: 0x1CF, bit 8 in [7]
        (5, 'amount_high', u16be),
        (7, 'type_high', u8, 0x80),
        (8, 'amount_low', u8),
    ))

    MAX = 0xFFFFFF

    @classmethod
    def of(cls, ground_zen, dropped=False):
        flag = DROPPED if dropped else 0
        return cls(entries=[{
            'id': g.id | flag, 'x': g.x, 'y': g.y, 'amount_high': min(g.zen, cls.MAX) >> 8,
            'amount_low': min(g.zen, cls.MAX) & 0xFF,
        } for g in ground_zen])


class ItemsGone(Packet):
    """C2 21: items on the ground out of view, picked up or gone."""
    code = C2, 0x21
    entry = Entry(count=(4, u8), size=2, fields=(
        (0, 'id', u16be),
    ))

    @classmethod
    def of(cls, ids):
        return cls(entries=[{'id': i} for i in ids])
