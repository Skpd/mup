"""
The vault keeper's warehouse: an account's zen and items (8 x 15 grid), loaded on the first open of the session
and kept on the connection, so every character of the account sees the same. It is saved with the character in one
transaction (GameServer.save): on close, logout and autosave. Items move with 24 (window 2), zen with 81.
"""
import logging
from mup.packet.client import CWarehouseMoney
from mup.packet.server import SItemList, STalk, SWarehouseMoney
from mup.server.ground import MAX_ZEN

logger = logging.getLogger(__name__)

MAX_STORED = 100_000_000  # zen in a vault, the usual 0.97 limit


def open_warehouse(game, c):
    """c's player talks to the vault keeper: the window, the items and the zen of the account's vault."""
    if c.warehouse is None:
        c.warehouse = game.characters.load_warehouse(c.acc.id)
    w = c.warehouse
    c.write(STalk(window=STalk.WAREHOUSE))
    c.write(SItemList.of(SItemList.SHOP, w.items))
    c.write(SWarehouseMoney(stored=w.zen, money=c.player.zen))


def is_open(c):
    return c.window is not None and c.window.kind == STalk.WAREHOUSE and c.warehouse is not None


def money(game, c, kind, amount):
    """81: c's player puts amount zen into the vault or takes it out. The answer has both totals, 0 refused."""
    p = c.player
    w = c.warehouse
    ok = is_open(c) and not p.dead and amount > 0
    if ok and kind == CWarehouseMoney.DEPOSIT:
        ok = amount <= p.zen and w.zen + amount <= MAX_STORED
        if ok:
            p.zen -= amount
            w.zen += amount
    elif ok and kind == CWarehouseMoney.WITHDRAW:
        ok = amount <= w.zen and p.zen + amount <= MAX_ZEN
        if ok:
            w.zen -= amount
            p.zen += amount
    else:
        ok = False
    if not ok:
        logger.debug('%s: zen %s %s refused', p.name, kind, amount)
    c.write(SWarehouseMoney(result=int(ok), stored=w.zen if w is not None else 0, money=p.zen))
    return ok
