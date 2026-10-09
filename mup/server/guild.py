"""
Guilds, see Guilds in docs/protocol-097.md. Kept in memory (GameServer.guilds by id, guild_of by character id),
every change written at once (mup.repository.guild). The connection of a member in game has its guild (c.guild).

The guild master NPC opens its window (54) for a player from level 100 without a guild, a yes (54) brings the name
and the mark (55), which create the guild (56). /guild at a master asks to join (50), the master answers (51). The
guild window (G) asks for the members (52), its X sends 53: a member leaves, the master puts one out, the master
leaving disbands the guild. Players see each other's guild with 5A (the guilds) and 5B (who is in which), 5D takes
it away. @ lines go to the members in game.
"""
import hmac
import logging
import re
from dataclasses import dataclass, field
from typing import List, Tuple
from mup.packet.server import (SGuildCreateResult, SGuildEditor, SGuildGone, SGuildLeaveResult, SGuildList,
                               SGuildMasterQuestion, SGuildRequest, SGuildResult, SObjectMessage)
from mup.server import view

logger = logging.getLogger(__name__)

MASTER_NPC = 241  # Royal Guard Captain Lorence
WINDOW = 'guild'  # mup.server.npc.Window kind while the guild master's window is open
CREATE_LEVEL = 100  # usual 0.97
JOIN_LEVEL = 6  # the client's message (51 7)
MAX_MEMBERS = 80  # usual: the master's level / 10, at most this
NAME = re.compile('[A-Za-z0-9]{4,8}')  # 8 bytes in the packets, the client's message for less than 4
ANSWER_TIME = 60.0  # seconds the master has to answer, mup's choice
CHAT = '@'
NO_GUILD = 0xFFFFFFFF  # a number no guild has: the trade window (37 [16..19]) shows no mark
LOW_LEVEL = 'Come back at level {}.'.format(CREATE_LEVEL)  # the master NPC's answers (01), mup's words
IN_GUILD = 'You are already in a guild.'


@dataclass(eq=False)
class Guild:
    id: int  # guilds.id, the guild number of the packets
    name: str
    mark: bytes  # 32 bytes, 64 colours of 4 bits
    members: List[Tuple[int, str]] = field(default_factory=list)  # (character id, name), the master first
    score: int = 0

    @property
    def master_id(self):
        return self.members[0][0]


def load(game):
    """The guilds from the database into game.guilds and game.guild_of."""
    game.guilds, game.guild_of = {}, {}
    for g, members in game.guild_store.load():
        if not members:
            logger.warning('Guild %s has no members, left out', g['name'])
            continue
        guild = Guild(g['id'], g['name'], bytes(g['mark'] or bytes(32)).ljust(32, b'\0'), list(members), g['score'])
        game.guilds[guild.id] = guild
        game.guild_of.update((character_id, guild) for character_id, _ in members)
    logger.info('%s guilds', len(game.guilds))


def online(game, g):
    """The connections of g's members in game."""
    return [c for c in game.playing() if c.guild is g]


def is_master(c):
    return c.guild is not None and c.guild.master_id == c.player.id


def say(c, npc, message):
    c.write(SObjectMessage(cid=npc.cid, message=message))


def talk(game, c, npc):
    """c's player talks to the guild master NPC: its window (54) from level 100 without a guild, else a word from
    it."""
    p = c.player
    if c.guild is not None:
        say(c, npc, IN_GUILD)
        return False
    if p.level < CREATE_LEVEL:
        say(c, npc, LOW_LEVEL)
        return False
    c.write(SGuildMasterQuestion())
    return True


def window_open(c):
    return c.window is not None and c.window.kind == WINDOW


def master_answer(game, c, yes):
    """54: yes goes on to the name and the mark (55), no closes the window."""
    if not window_open(c):
        return
    if yes:
        c.write(SGuildEditor())
    else:
        c.window = None


def cancel(game, c):
    """57: the window closed at the mark."""
    if window_open(c):
        c.window = None


def create(game, c, name, mark):
    """55: c's player creates the guild name with mark, as its master. Answered with 56, the players around see the
    guild."""
    p = c.player
    if not window_open(c):
        logger.debug('%s: 55 without the guild master\'s window', p.name)
        return False
    if c.guild is not None or p.level < CREATE_LEVEL:
        result = SGuildCreateResult.IN_GUILD
    elif len(name.encode('latin-1')) < 4:
        result = SGuildCreateResult.SHORT
    elif not NAME.fullmatch(name) or not any(mark) or game.guild_store.name_taken(name):
        result = SGuildCreateResult.TAKEN
    else:
        g = Guild(game.guild_store.create(name, p.id, mark), name, bytes(mark), [(p.id, p.name)])
        game.guilds[g.id] = g
        game.guild_of[p.id] = g
        c.guild = g
        c.window = None
        logger.info('%s creates the guild %s', p.name, name)
        c.write(SGuildCreateResult(result=SGuildCreateResult.CREATED))
        joined(game, c)
        return True
    logger.debug('%s can\'t create the guild %r: %s', p.name, name, result)
    c.write(SGuildCreateResult(result=result))
    return False


def joined(game, c):
    """c's player is in its guild now: it and the players who see it are shown so (5A, 5B)."""
    view.guilds(c, [c])
    for o in view.viewers(game, c):
        view.guilds(o, [c])


def gone(game, c):
    """c's player isn't in a guild anymore: 5D to it and the players who see it."""
    packet = SGuildGone(cid=c.cid)
    c.write(packet)
    for o in view.viewers(game, c):
        o.write(packet)


def request(game, c, cid):
    """50: c's player asks the guild master cid to join its guild. The master gets the question, a refusal goes back
    as 51."""
    p = c.player
    master = game.connections.get(cid)
    if p.level < JOIN_LEVEL:
        result = SGuildResult.LEVEL
    elif c.guild is not None:
        result = SGuildResult.IN_GUILD
    elif master is None or master.player is None or not master.playing or master not in c.view:
        result = SGuildResult.GONE
    elif not is_master(master):
        result = SGuildResult.NOT_MASTER
    elif len(master.guild.members) >= capacity(master):
        result = SGuildResult.FULL
    elif master.player.dead or master.trade is not None or master.window is not None or asked(game, master):
        result = SGuildResult.BUSY
    else:
        master.guild_question = (c, game.now)
        master.write(SGuildRequest(cid=c.cid))
        logger.debug('%s asks %s to join %s', p.name, master.player.name, master.guild.name)
        return True
    logger.debug('%s can\'t join the guild of %s: %s', p.name, cid, result)
    c.write(SGuildResult(result=result))
    return False


def capacity(master):
    """Members a guild master's guild may have: its level / 10, usual."""
    return min(MAX_MEMBERS, master.player.level // 10)


def asked(game, master):
    """The master has a question it can still answer."""
    q = master.guild_question
    return q is not None and q[0].player is not None and game.now <= q[1] + ANSWER_TIME


def answer(game, c, yes, cid):
    """51: the master c answers the join request of cid: the asker joins (51 1) or hears no (51 0)."""
    q = c.guild_question
    if q is None or q[0].cid != cid:
        return False
    asker, asked_at = q
    c.guild_question = None
    if asker.player is None or not asker.playing or game.now > asked_at + ANSWER_TIME:
        return False
    if not yes:
        asker.write(SGuildResult(result=SGuildResult.REFUSED))
        return False
    g = c.guild
    if asker.guild is not None or not is_master(c):
        result = SGuildResult.IN_GUILD if asker.guild is not None else SGuildResult.NOT_MASTER
        asker.write(SGuildResult(result=result))
        return False
    if len(g.members) >= capacity(c):
        asker.write(SGuildResult(result=SGuildResult.FULL))
        return False
    p = asker.player
    game.guild_store.add_member(g.id, p.id)
    g.members.append((p.id, p.name))
    game.guild_of[p.id] = g
    asker.guild = g
    logger.info('%s joins the guild %s', p.name, g.name)
    asker.write(SGuildResult(result=SGuildResult.JOINED))
    joined(game, asker)
    send_list(game, c)
    return True


def send_list(game, c):
    """52: the members of c's guild, who is in game, the guild's score. Without a guild an empty list."""
    g = c.guild
    if g is None:
        c.write(SGuildList(result=0))
        return
    in_game = {o.player.id for o in online(game, g)}
    c.write(SGuildList.of([(name, character_id in in_game) for character_id, name in g.members], g.score))


def leave(game, c, name, code):
    """53: c's player leaves its guild (its own name), or puts the member name out as the master. The master leaving
    disbands the guild. The personal code is checked."""
    p = c.player
    g = c.guild
    if g is None:
        return False
    if not hmac.compare_digest(code.encode('latin-1'), c.acc.personal_code.encode('latin-1')):
        c.write(SGuildLeaveResult(result=SGuildLeaveResult.WRONG_CODE))
        return False
    if name.lower() == p.name.lower():
        if is_master(c):
            disband(game, g)
        else:
            remove(game, g, p.id)
            c.write(SGuildLeaveResult(result=SGuildLeaveResult.LEFT))
            logger.info('%s leaves the guild %s', p.name, g.name)
        return True
    member = next(((i, n) for i, n in g.members if n.lower() == name.lower()), None)
    if not is_master(c) or member is None:
        c.write(SGuildLeaveResult(result=SGuildLeaveResult.NOT_MASTER))
        return False
    other = remove(game, g, member[0])
    if other is not None:
        other.write(SGuildLeaveResult(result=SGuildLeaveResult.PUT_OUT))
    logger.info('%s puts %s out of the guild %s', p.name, member[1], g.name)
    send_list(game, c)
    return True


def remove(game, g, character_id):
    """The member leaves g: stored, its connection in game loses the guild (5D around it). The connection, None
    when the member isn't in game."""
    game.guild_store.remove_member(character_id)
    g.members = [m for m in g.members if m[0] != character_id]
    game.guild_of.pop(character_id, None)
    c = next((o for o in online(game, g) if o.player.id == character_id), None)
    if c is not None:
        c.guild = None
        gone(game, c)
    return c


def disband(game, g):
    """The guild is gone: its members in game hear it (53 4) and lose it."""
    game.guild_store.delete(g.id)
    del game.guilds[g.id]
    for character_id, _ in g.members:
        game.guild_of.pop(character_id, None)
    for c in online(game, g):
        c.guild = None
        c.write(SGuildLeaveResult(result=SGuildLeaveResult.DISBANDED))
        gone(game, c)
    logger.info('The guild %s is disbanded', g.name)


def character_deleted(game, character_id):
    """A character is deleted: its guild loses it, a master's guild is disbanded."""
    g = game.guild_of.get(character_id)
    if g is None:
        return
    if g.master_id == character_id:
        disband(game, g)
    else:
        remove(game, g, character_id)


def chat(game, c, packet):
    """An @ line of c's player to the members of its guild in game. False without a guild."""
    if c.guild is None:
        return False
    for o in online(game, c.guild):
        o.write(packet)
    return True


def number(c):
    """The guild number of c's player for the trade window's mark, NO_GUILD without a guild."""
    return c.guild.id if c.guild is not None else NO_GUILD
