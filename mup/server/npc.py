"""
NPCs: the later server's section 0 spawns of the types this client has (mup.server.monster.NPC_TYPES), standing at
their spot in the monsters' ids, shown with 13. Nobody hits them, only traps act (mup.server.ai). Talking (30) opens
the NPC's window, one at a time, kept on the connection until the client closes it (31, 82, 87: it waits for 87
back), the player walks away, dies, changes the map or leaves the game. Nobody talks during a trade. Sevina opens
the quest window (mup.server.quest), the guild master its own (mup.server.guild), Charon Devil Square's
(mup.server.devil_square), shops send murderers away (mup.server.pk).
"""
import logging
from dataclasses import dataclass
from mup.model.monster import Monster
from mup.packet.server import SChaosClosed, SObjectMessage, STalk, SWarehouseClosed
from mup.server import chaos, devil_square, guild, pk, quest, shop, warehouse
from mup.server.world import distance

logger = logging.getLogger(__name__)

TALK_RANGE = 5  # tiles: the client talks next to the NPC, the window stays open this close. mup's choice
NO_MURDERERS = 'I do not deal with murderers.'  # a shop's answer to a murderer (01), mup's words
VAULT_KEEPER = 240
CHAOS_GOBLIN = 238


@dataclass(eq=False)
class Window:
    """An NPC window open on a connection: kind as in 30 (STalk), quest.WINDOW or guild.WINDOW, the NPC."""
    kind: int
    npc: Monster


def window_of(game, npc_type):
    """The window an NPC type opens, None for those mup has nothing for (guards, ...)."""
    if npc_type == quest.NPC:
        return quest.WINDOW
    if npc_type == guild.MASTER_NPC:
        return guild.WINDOW
    if npc_type == devil_square.CHARON:
        return STalk.DEVIL_SQUARE
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
    if p.dead or c.trade is not None or npc is None or not npc.npc or npc not in c.view or distance(p.x, p.y, npc.x, npc.y) > TALK_RANGE:
        logger.debug('%s can\'t talk to %s', p.name, cid)
        return False
    kind = window_of(game, npc.type_id)
    if kind is None:
        logger.debug('%s talks to %s, nothing to say', p.name, npc.info.name)
        return False
    if kind == STalk.SHOP and pk.refused(c):
        logger.debug('%s talks to %s, a murderer', p.name, npc.info.name)
        c.write(SObjectMessage(cid=npc.cid, message=NO_MURDERERS))
        return False
    close(game, c)
    c.window = Window(kind, npc)
    logger.debug('%s talks to %s', p.name, npc.info.name)
    if kind == STalk.SHOP:
        shop.open_shop(game, c, npc)
    elif kind == STalk.WAREHOUSE:
        warehouse.open_warehouse(game, c)
    elif kind == STalk.CHAOS_MACHINE:
        chaos.open_box(game, c)
    elif not (quest.talk(game, c) if kind == quest.WINDOW else guild.talk(game, c, npc) if kind == guild.WINDOW
              else devil_square.talk(game, c)):
        c.window = None
        return False
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
    if notify and w.kind not in (quest.WINDOW, guild.WINDOW):  # 82 doesn't close these, what they send is refused
        c.write(SChaosClosed() if w.kind == STalk.CHAOS_MACHINE else SWarehouseClosed())


def close_chaos(game, c):
    """87: the chaos machine's close button, sent with an empty box. The client closes the window only when 87 comes
    back, so it always does."""
    if chaos.is_open(c):
        close(game, c, notify=True)
    else:
        c.write(SChaosClosed())


def check(game, c):
    """The game tick: c's window closes when its player died or walked away from the NPC."""
    w = c.window
    p = c.player
    if w is not None and (p.dead or p.map_id != w.npc.map_id
                          or distance(p.x, p.y, w.npc.x, w.npc.y) > TALK_RANGE):
        logger.debug('%s left %s', p.name, w.npc.info.name)
        close(game, c, notify=True)
