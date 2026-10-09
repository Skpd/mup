"""
Chat (00) and whispers (02), see the Chat section of docs/protocol-097.md. A line goes to every player in game under
the speaker's name, the speaker too (the client doesn't show its own). ~ lines go to the party only, @ lines to the
guild. A whisper reaches a player by name on any map, 0C tells the sender nobody has it.
"""
import logging
from mup.packet.server import SChat, SWhisper, SWhisperFailed
from mup.server import guild, party

logger = logging.getLogger(__name__)

MESSAGE_SIZE = 60  # bytes the client copies, the zero included


def line(message):
    """message cut to what the client shows."""
    return message.encode('latin-1')[:MESSAGE_SIZE - 1].decode('latin-1')


def say(game, c, message):
    """c's player says message: to everyone in game, a ~ line to its party."""
    p = c.player
    packet = SChat(name=p.name, message=line(message))
    if message.startswith(party.CHAT):
        if party.chat(game, c, packet):
            logger.info('Party %s: %s', p.name, message)
        return
    if message.startswith(guild.CHAT):
        if guild.chat(game, c, packet):
            logger.info('Guild %s: %s', p.name, message)
        return
    logger.info('Say %s: %s', p.name, message)
    for o in game.playing():
        if o.playing:
            o.write(packet)


def find(game, name):
    """The connection playing the character named name (any case), None when nobody does."""
    name = name.lower()
    return next((c for c in game.playing() if c.playing and c.player.name.lower() == name), None)


def whisper(game, c, name, message):
    """c's player whispers message to the character name: 02 to it, 0C to c when it isn't in game."""
    target = find(game, name)
    if target is None:
        logger.debug('%s whispers to %s, not in game', c.player.name, name)
        c.write(SWhisperFailed())
        return False
    logger.info('Whisper %s to %s: %s', c.player.name, target.player.name, message)
    target.write(SWhisper(name=c.player.name, message=line(message)))
    return True
