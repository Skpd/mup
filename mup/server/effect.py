"""
Timed effects of skills on players and monsters: poison, ice, the elf's buffs, the knight's defense. The object's
state holds the bits the clients show (12 [+16] / 13 [+4..5]), 19 with bit 15 sets them in the clients, 1B clears
them (client 0x418500). Durations and strengths are the usual 0.97 values or mup's choice, see the constants.
"""
from dataclasses import dataclass
from mup.model.monster import Monster
from mup.packet.server import SEffectEnded
from mup.server import view

POISON, ICE, DEFENSE, GREATER_DEFENSE, GREATER_DAMAGE = 1, 7, 18, 27, 28
# skill number -> the bit of its effect in the objects in view packets, the ones 1B clears
BITS = {POISON: 0x01, ICE: 0x02, GREATER_DAMAGE: 0x04, GREATER_DEFENSE: 0x08, 16: 0x100}

POISON_TIME = 10.0  # seconds, mup's choice
POISON_INTERVAL = 2.0
POISON_DAMAGE = 3  # % of the life left per interval, at least 1
ICE_TIME = 10.0  # the monster walks at half speed
DEFENSE_TIME = 3.0  # damage taken halved, mup's choice
BUFF_TIME = 60.0  # greater defense / damage, usual


@dataclass
class Effect:
    until: float
    value: int = 0  # what a buff adds
    source: object = None  # connection whose skill it was: poison damage counts as its hits
    next_at: float = 0.0  # poison's next damage


def apply(game, obj, number, duration, value=0, source=None):
    """obj (a connection or a monster) gets the effect of skill number for duration seconds, a running one starts
    again."""
    holder = holder_of(obj)
    now = game.now
    holder.effects[number] = Effect(now + duration, value, source, now + POISON_INTERVAL)
    holder.state |= BITS.get(number, 0)
    game.affected.add(obj)


def has(obj, number):
    return number in holder_of(obj).effects


def value(obj, number):
    e = holder_of(obj).effects.get(number)
    return e.value if e is not None else 0


def end(game, obj, number):
    """The effect ends: its bit goes, the clients that see obj (and its own) get 1B."""
    holder = holder_of(obj)
    if holder.effects.pop(number, None) is None:
        return
    bit = BITS.get(number, 0)
    holder.state &= ~bit
    if bit:
        packet = SEffectEnded(skill=number, cid=obj.cid)
        for c in view.viewers(game, obj):
            c.write(packet)
        if not isinstance(obj, Monster):
            obj.write(packet)


def clear(game, obj):
    """All effects end without packets: obj died, left or respawned, the clients get it new anyway."""
    holder = holder_of(obj)
    holder.effects.clear()
    holder.state = 0
    game.affected.discard(obj)


def tick(game, now):
    """Poison hurts, effects run out."""
    from mup.server import combat, pk
    for obj in list(game.affected):
        holder = holder_of(obj)
        if holder is None or holder.dead:
            game.affected.discard(obj)
            continue
        for number, e in list(holder.effects.items()):
            if number == POISON and now >= e.next_at:
                e.next_at = now + POISON_INTERVAL
                source = e.source if e.source is not None and e.source.player is not None else None
                if source is None:
                    pass
                elif isinstance(obj, Monster):
                    combat.hit_monster(source, obj, max(1, obj.life * POISON_DAMAGE // 100), magic=True)
                elif pk.may_hit(game, source, obj):
                    combat.player_hit(game, source, obj, max(1, holder.life * POISON_DAMAGE // 100))
                if holder.dead:
                    break
            if now >= e.until:
                end(game, obj, number)
        if not holder.effects or holder.dead:
            game.affected.discard(obj)


def holder_of(obj):
    """Where the effects live: the monster, or the player of a connection (None when it left)."""
    return obj if isinstance(obj, Monster) else obj.player
