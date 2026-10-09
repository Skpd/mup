"""
Trades between two players (36..3D, see the Trade section of docs/protocol-097.md). A player asks one next to it
(36), the other answers (37), then each puts items into its 8 x 4 grid (24 window 1, Player.trade_box) and zen (3A),
the partner sees them (38, 39, 3B). Any change takes back both oks (3C). When both are ok the items and zen change
hands at once and both characters are saved with the trade in one transaction. Any other end (cancel, walking away,
a map change, death, leaving the game) gives everything back.

The trade lives on both connections (c.trade). The zen put in stays in the player's money until the exchange, the
client is shown what is left (22 FE). Items put in leave the inventory: they are stored with the character (owner
'trade') and come back into the inventory when the trade ends or, after a crash, on the next entry.
"""
import logging
from dataclasses import dataclass
from mup.packet.server import (SMoveItemResult, SPartnerZen, SPickUpResult, STradeAnswer, STradeEnd, STradeItem,
                               STradeItemGone, STradeOk, STradeRequest, STradeZen)
from mup.server import guild, inventory
from mup.server.ground import MAX_ZEN
from mup.server.world import distance

logger = logging.getLogger(__name__)

MIN_LEVEL = 6  # the client's: no /trade below it (Text 478)
TRADE_RANGE = 5  # tiles: the client asks within 1, the trade stays open this close. mup's choice, like talking
ANSWER_TIME = 30.0  # seconds the question waits for the answer, mup's choice
TRADE = SMoveItemResult.TRADE  # the 24 window of the own grid


@dataclass(eq=False)
class Side:
    """One side of a trade: the connection, the part of its player's money put in, its ok."""
    c: object
    zen: int = 0
    ok: bool = False


@dataclass(eq=False)
class Trade:
    """a asked b at asked_at. open: b said yes, the window is open on both."""
    a: Side
    b: Side
    asked_at: float
    open: bool = False

    def side(self, c):
        return self.a if self.a.c is c else self.b

    def partner(self, c):
        return self.b if self.a.c is c else self.a

    @property
    def sides(self):
        return self.a, self.b


def free(c):
    """c may start a trade: in game, alive, from level 6, no NPC window or trade, nothing left in its trade box."""
    p = c.player
    return (p is not None and c.playing and not p.dead and p.level >= MIN_LEVEL and c.window is None
            and c.trade is None and not p.trade_box)


def near(c, other):
    p, o = c.player, other.player
    return (p is not None and o is not None and not p.dead and not o.dead and p.map_id == o.map_id
            and distance(p.x, p.y, o.x, o.y) <= TRADE_RANGE)


def request(game, c, cid):
    """36: c's player asks the player cid to trade. Refused with 37 2 when either can't."""
    other = game.connections.get(cid)
    if other is None or other is c or other not in c.view or not free(c) or not free(other) or not near(c, other):
        logger.debug('%s can\'t trade with %s', c.player.name, cid)
        c.write(STradeAnswer(result=STradeAnswer.BUSY))
        return False
    c.trade = other.trade = Trade(Side(c), Side(other), game.now)
    other.write(STradeRequest(name=c.player.name))
    logger.debug('%s asks %s to trade', c.player.name, other.player.name)
    return True


def answer(game, c, yes):
    """37: c's player answers the question: the window opens on both (37 1) or the asker hears no (37 0)."""
    t = c.trade
    if t is None or t.open or t.b.c is not c:
        return
    asker = t.a.c
    if not yes:
        logger.debug('%s doesn\'t trade with %s', c.player.name, asker.player.name)
        c.trade = asker.trade = None
        asker.write(STradeAnswer(result=STradeAnswer.REFUSED))
        return
    if not near(c, asker):
        cancel(game, c)
        return
    t.open = True
    for side in t.sides:
        partner = t.partner(side.c).c
        side.c.write(STradeAnswer(result=STradeAnswer.OPEN, name=partner.player.name, level=partner.player.level,
                                  guild=guild.number(partner)))
    logger.info('%s and %s trade', asker.player.name, c.player.name)


def is_open(c):
    return c.trade is not None and c.trade.open


def moved(game, c, source_window, source, target_window, target, item):
    """An item of c's player moved (24) out of or into its trade grid: the partner sees it, the oks are off."""
    t = c.trade
    other = t.partner(c).c
    if source_window == TRADE:
        other.write(STradeItemGone(slot=source))
    if target_window == TRADE:
        other.write(STradeItem(slot=target, item=item.encode()))
    changed(t)


def changed(t):
    """What one side gives changed: whoever was ok isn't any more, both clients see it."""
    for side in t.sides:
        if side.ok:
            side.ok = False
            side.c.write(STradeOk(state=STradeOk.OWN_OFF))
            t.partner(side.c).c.write(STradeOk(state=STradeOk.PARTNER_OFF))


def zen(game, c, amount):
    """3A: c's player puts amount zen into the trade, replacing what it put in. The money shown is what is left."""
    if not is_open(c):
        c.write(STradeZen(result=0))
        return False
    t = c.trade
    side = t.side(c)
    p = c.player
    ok = 0 <= amount <= p.zen
    side.zen = amount if ok else 0
    c.write(SPickUpResult.zen(p.zen - side.zen))
    c.write(STradeZen(result=int(ok)))
    t.partner(c).c.write(SPartnerZen(amount=side.zen))
    changed(t)
    return ok


def ok(game, c, value):
    """3C: c's player is ok with the trade or not any more. Both ok: the exchange."""
    if not is_open(c):
        return
    t = c.trade
    side = t.side(c)
    side.ok = bool(value)
    t.partner(c).c.write(STradeOk(state=STradeOk.PARTNER_ON if side.ok else STradeOk.PARTNER_OFF))
    if t.a.ok and t.b.ok:
        exchange(game, t)


def placement(items_in, given):
    """Inventory slot -> item for the items given (slot -> item) in the grid of items_in, None when they don't all
    fit. The bigger ones first."""
    used = inventory.taken(items_in)
    placed = {}
    for item in sorted(given.values(), key=lambda i: -i.info.width * i.info.height):
        slot = inventory.free_slot(items_in, item.info, used=used)
        if slot is None:
            return None
        placed[slot] = item
        used |= inventory.tiles(slot, item.info)
    return placed


def exchange(game, t):
    """Both are ok: each one's items go into the other's inventory and the zen changes hands, at once and saved
    together. Without room on a side (or the money above the limit) the trade ends with everything given back."""
    a, b = t.sides
    pa, pb = a.c.player, b.c.player
    to_b = placement(pb.inventory, pa.trade_box)
    to_a = placement(pa.inventory, pb.trade_box)
    room_a = to_a is not None and pa.zen - a.zen + b.zen <= MAX_ZEN
    room_b = to_b is not None and pb.zen - b.zen + a.zen <= MAX_ZEN
    if not (room_a and room_b):
        logger.info('%s and %s: no room for the trade', pa.name, pb.name)
        for side, room in ((a, room_a), (b, room_b)):
            end(game, side.c, STradeEnd.CANCELED if room else STradeEnd.NO_ROOM)
        return

    given_a, given_b = list(pa.trade_box.values()), list(pb.trade_box.values())
    pa.trade_box.clear()
    pb.trade_box.clear()
    pb.inventory.update(to_b)
    pa.inventory.update(to_a)
    pa.zen += b.zen - a.zen
    pb.zen += a.zen - b.zen
    logger.info('%s gives %s and %s zen to %s for %s and %s zen', pa.name, given_a, a.zen, pb.name, given_b, b.zen)
    game.save_trade((a.c, a.zen, given_a), (b.c, b.zen, given_b))
    for side in t.sides:
        end(game, side.c, STradeEnd.DONE)


def cancel(game, c, leaving=False):
    """c's trade ends without an exchange: both get what they put in back. A question still waiting is called off
    (3D 3). leaving: c leaves the game, its client gets nothing."""
    t = c.trade
    if t is None:
        return
    result = STradeEnd.CANCELED if t.open else STradeEnd.REQUEST_CANCELED
    logger.debug('trade of %s and %s canceled', t.a.c.player.name, t.b.c.player.name)
    for side in t.sides:
        end(game, side.c, result, notify=not (leaving and side.c is c))


def end(game, c, result, notify=True):
    """c's side of a trade ends with result (3D): what is left in its grid goes back, its client gets the
    inventory and the money when the window was open, it closed both grids."""
    t = c.trade
    c.trade = None
    if c.player is None:
        return
    return_items(game, c, notify=False)
    if notify and c.connected:
        c.write(STradeEnd(result=result))
        if t.open:
            inventory.send(c)
            c.write(SPickUpResult.zen(c.player.zen))


def return_items(game, c, notify=True):
    """The items in c's player's trade box go back into the inventory where they fit, the rest stays for the next
    entry. notify: the client gets the inventory (F3 10) when something moved."""
    p = c.player
    moved_any = False
    for slot in sorted(p.trade_box):
        item = p.trade_box[slot]
        target = inventory.free_slot(p.inventory, item.info)
        if target is None:
            continue
        del p.trade_box[slot]
        p.inventory[target] = item
        moved_any = True
    if p.trade_box:
        logger.warning('%s: no room in the inventory, %s stay in the trade box', p.name, list(p.trade_box.values()))
    if moved_any and notify:
        inventory.send(c)
    return moved_any


def check(game, c):
    """The game tick: c's trade ends when the partner is gone or away, or the question waited too long."""
    t = c.trade
    if t is None:
        return
    other = t.partner(c).c
    if other.player is None or not near(c, other) or not t.open and game.now > t.asked_at + ANSWER_TIME:
        cancel(game, c)
