"""
NPCs: the later server's section 0 spawns of the types this client has (mup.server.monster.NPC_TYPES), standing at
their spot in the monsters' ids, shown with 13. Nobody hits them, only traps act (mup.server.ai). Talking (30) opens
the NPC's window, one at a time, kept on the connection until the client closes it (31, 82, 87), the player walks
away, dies, changes the map or leaves the game.
"""
import logging
from dataclasses import dataclass
from mup.model.monster import Monster
from mup.packet.server import SChaosClosed, STalk, SWarehouseClosed
from mup.server import chaos, shop, warehouse
from mup.server.world import distance

logger = logging.getLogger(__name__)

TALK_RANGE = 5  # tiles: the client talks next to the NPC, the window stays open this close. mup's choice
VAULT_KEEPER = 240
CHAOS_GOBLIN = 238


@dataclass(eq=False)
class Window:
    """An NPC window open on a connection: kind as in 30 (STalk), the NPC."""
    kind: int
    npc: Monster


def window_of(game, npc_type):
    """The window an NPC type opens, None for those mup has nothing for yet (guards, quests, Devil Square)."""
    if npc_type == VAULT_KEEPER:
        return STalk.WAREHOUSE
    if npc_type == CHAOS_GOBLIN:
        return STalk.CHAOS_MACHINE
    if npc_type in game.shops:
        return STalk.SHOP
    return None


def talk(game, c, cid):
    """30: c's player talks to the NPC cid, near and in view: the window of the NPC replaces the one open."""
    p = c.player
    npc = game.monsters.get(cid)
    if p.dead or npc is None or not npc.npc or npc not in c.view or distance(p.x, p.y, npc.x, npc.y) > TALK_RANGE:
        logger.debug('%s can\'t talk to %s', p.name, cid)
        return False
    kind = window_of(game, npc.type_id)
    if kind is None:
        logger.debug('%s talks to %s, nothing to say', p.name, npc.info.name)
        return False
    close(game, c)
    c.window = Window(kind, npc)
    logger.debug('%s talks to %s', p.name, npc.info.name)
    if kind == STalk.SHOP:
        shop.open_shop(game, c, npc)
    elif kind == STalk.WAREHOUSE:
        warehouse.open_warehouse(game, c)
    else:
        chaos.open_box(game, c)
    return True


def close(game, c, notify=False, leaving=False):
    """Closes c's window: the items in the chaos machine go back (F3 10), the vault is saved with the character.
    notify: the client hears of it (82 / 87), for the closes it doesn't do itself. leaving: c leaves the game, which
    saves, the client gets nothing."""
    w = c.window
    if w is None:
        return
    c.window = None
    p = c.player
    if w.kind == STalk.CHAOS_MACHINE and p.chaos_box:
        chaos.return_items(game, c, notify=not leaving)
        c.stale_box = not leaving  # the client's box may still show them
    elif w.kind == STalk.WAREHOUSE and not leaving:
        game.save(c)
    if notify:
        c.write(SChaosClosed() if w.kind == STalk.CHAOS_MACHINE else SWarehouseClosed())


def check(game, c):
    """The game tick: c's window closes when its player died or walked away from the NPC."""
    w = c.window
    p = c.player
    if w is not None and (p.dead or p.map_id != w.npc.map_id
                          or distance(p.x, p.y, w.npc.x, w.npc.y) > TALK_RANGE):
        logger.debug('%s left %s', p.name, w.npc.info.name)
        close(game, c, notify=True)
