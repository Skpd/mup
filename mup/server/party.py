"""
Parties (40..44, see the Party section of docs/protocol-097.md), in memory. A player asks one in view (40), who
answers (41) with the asker's cid. Up to 5 members, the first is the leader: only it asks others in and may put
anyone out (43), the others may leave. Every member gets the list (42) on each change and the life of all (44) every
few seconds, with the list again when someone moved. One left alone and a player leaving the game are out.
Party chat is a ~ line, kills are shared (mup.server.experience).
"""
import logging
from dataclasses import dataclass, field
from typing import List
from mup.packet.server import SPartyLeft, SPartyList, SPartyLife, SPartyRequest, SPartyResult
from mup.server import pk

logger = logging.getLogger(__name__)

MAX_MEMBERS = 5  # usual 0.97
LEVEL_GAP = 120  # the client has the message (41 5)
ANSWER_TIME = 60.0  # seconds a question can be answered, mup's choice
UPDATE_INTERVAL = 2.0  # seconds between the life updates (44), mup's choice
CHAT = '~'


@dataclass(eq=False)
class Party:
    """members: connections, the leader first, in the order of the client's list."""
    members: List[object] = field(default_factory=list)
    next_update: float = 0.0
    shown: tuple = ()  # what the last 42 showed

    @property
    def leader(self):
        return self.members[0]


def request(game, c, cid):
    """40: c's player asks the player cid to join its party. The other gets the question, a refusal goes back to c
    as 41."""
    p = c.player
    other = game.connections.get(cid)
    party = c.party
    if other is None or other.player is None or not other.playing or other not in c.view:
        result = SPartyResult.GONE
    elif other is c or p.dead or party is not None and party.leader is not c or pk.refused(c) or pk.refused(other):
        result = SPartyResult.FAILED
    elif party is not None and len(party.members) >= MAX_MEMBERS:
        result = SPartyResult.FULL
    elif other.party is not None:
        result = SPartyResult.IN_PARTY
    elif abs(p.level - other.player.level) >= LEVEL_GAP:
        result = SPartyResult.LEVEL_GAP
    else:
        other.party_question = (c, game.now)
        other.write(SPartyRequest(cid=c.cid))
        logger.debug('%s asks %s to party', p.name, other.player.name)
        return True
    logger.debug('%s can\'t ask %s to party: %s', p.name, cid, result)
    c.write(SPartyResult(result=result))
    return False


def answer(game, c, yes, cid):
    """41: c's player answers the question of cid: it joins the asker's party, which is made when there is none."""
    question = c.party_question
    if question is None or question[0].cid != cid:
        return
    asker, asked_at = question
    c.party_question = None
    if asker.player is None or not asker.playing or game.now > asked_at + ANSWER_TIME:
        c.write(SPartyResult(result=SPartyResult.GONE))
        return
    if not yes:
        asker.write(SPartyResult(result=SPartyResult.REFUSED))
        return
    party = asker.party
    result = None
    if c.party is not None:
        result = SPartyResult.IN_PARTY
    elif party is not None and party.leader is not asker or pk.refused(c) or pk.refused(asker):
        result = SPartyResult.FAILED
    elif party is not None and len(party.members) >= MAX_MEMBERS:
        result = SPartyResult.FULL
    if result is not None:
        asker.write(SPartyResult(result=result))
        c.write(SPartyResult(result=result))
        return
    if party is None:
        party = asker.party = Party([asker])
        game.parties.add(party)
    party.members.append(c)
    c.party = party
    logger.info('%s joins the party of %s', c.player.name, asker.player.name)
    changed(game, party)


def remove(game, c, member):
    """43: c's player takes the member at index out of its party: itself, or anyone when it is the leader."""
    party = c.party
    if party is None or not 0 <= member < len(party.members):
        return
    target = party.members[member]
    if target is not c and party.leader is not c:
        return
    leave(game, target)


def leave(game, c, notify=True):
    """c leaves its party (43 to it unless not notify), the others get the list. One left alone is out too, the
    party is gone. When the leader leaves the next member leads (mup's choice)."""
    party = c.party
    if party is None:
        return
    party.members.remove(c)
    c.party = None
    logger.info('%s leaves the party', c.player.name if c.player is not None else c.cid)
    if notify:
        c.write(SPartyLeft())
    if len(party.members) == 1:
        last = party.members.pop()
        last.party = None
        last.write(SPartyLeft())
    if party.members:
        changed(game, party)
    else:
        game.parties.discard(party)


def changed(game, party):
    """The members changed: the list and the life to all of them."""
    party.shown = ()
    update(game, party, game.now)


def update(game, party, now):
    """The life of the members (44) to all, the list (42) when it differs from the last one shown."""
    players = [m.player for m in party.members]
    shown = tuple((p.name, p.map_id, p.x, p.y, p.life, p.max_life) for p in players)
    packets = [SPartyLife.of(players)]
    if shown != party.shown:
        party.shown = shown
        packets.insert(0, SPartyList.of(players))
    for m in party.members:
        for packet in packets:
            m.write(packet)
    party.next_update = now + UPDATE_INTERVAL


def tick(game, now):
    """The game tick: the parties due for an update get it."""
    for party in list(game.parties):
        if now >= party.next_update and all(m.player is not None for m in party.members):
            update(game, party, now)


def chat(game, c, packet):
    """A ~ line of c's player goes to the members of its party, c too. Nothing without a party."""
    if c.party is None:
        return False
    for m in c.party.members:
        m.write(packet)
    return True
