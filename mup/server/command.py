"""
GM commands: chat lines starting with / from accounts with the GM ctl code (bin/account.py gm). The answer is a
notice to the GM only.

/level n            level n with the level up points of the levels gained, the exp of the level
/points n           n level up points
/zen n              n zen
/item g i [l s u o e]   an item of group g index i into the inventory: level, skill 0/1, luck 0/1, option 0..7,
                    excellent bits
/move map x y       to x, y of a map
/skill n            learns skill number n
/heal               full life and mana
/pk n               pk count n (-3..100), the pk level follows it
/ds                 Devil Square: Charon lets players in now, the round starts after the configured entry time
"""
import logging
from mup.model.account import GM
from mup.model.item import GROUP_SIZE
from mup.model.player import MAX_LEVEL, level_exp
from mup.packet.server import SAnnouncement, SLevelUp, SLife, SMana, SMapMove, SRespawn
from mup.server import devil_square, inventory, pk, skill, stats
from mup.server.ground import MAX_ZEN

logger = logging.getLogger(__name__)

PREFIX = '/'


class Refused(Exception):
    """A command that can't be done, the message goes to the GM."""


def is_command(c, message):
    return message.startswith(PREFIX) and c.acc is not None and c.acc.ctl_code & GM


def run(game, c, message):
    """Runs a GM command line of c's player, answers with a notice."""
    words = message[len(PREFIX):].split()
    if not words:
        return
    name, args = words[0].lower(), words[1:]
    command = COMMANDS.get(name)
    try:
        if command is None:
            raise Refused('unknown command, one of: ' + ' '.join(sorted(COMMANDS)))
        try:
            numbers = [int(a) for a in args]
        except ValueError:
            raise Refused('numbers expected')
        answer = command(game, c, *numbers)
    except TypeError:
        answer = 'wrong arguments, see mup/server/command.py'
    except Refused as e:
        answer = str(e)
    logger.info('%s: %s -> %s', c.player.name, message, answer)
    c.write(SAnnouncement(message=answer.encode('latin-1', 'replace').decode('latin-1')))


def between(value, low, high, what):
    if not low <= value <= high:
        raise Refused('{} {}..{}'.format(what, low, high))
    return value


def refresh(game, c):
    """The client takes exp and money from F3 04: c's player appears again where it stands with them."""
    p = c.player
    game.relocate(c, p.map_id, p.x, p.y, p.direction, SRespawn.of)


def level(game, c, n):
    p = c.player
    n = between(n, 1, MAX_LEVEL, 'level')
    if n > p.level:
        p.free_points += (n - p.level) * p.class_info.level_points
    p.level = n
    p.exp = level_exp(n)
    stats.update(c, notify=False)  # F3 05 carries the new maximum life and mana
    p.life, p.mana = p.max_life, p.max_mana
    c.write(SLevelUp(level=p.level, points=p.free_points, max_life=p.max_life, max_mana=p.max_mana))
    refresh(game, c)
    return 'level {}'.format(n)


def points(game, c, n):
    p = c.player
    p.free_points = between(n, 0, 0xFFFF, 'points')
    c.write(SLevelUp(level=p.level, points=p.free_points, max_life=p.max_life, max_mana=p.max_mana))
    return '{} points'.format(n)


def zen(game, c, n):
    c.player.zen = between(n, 0, MAX_ZEN, 'zen')
    refresh(game, c)
    return '{} zen'.format(n)


def item(game, c, group, index, level=0, has_skill=0, luck=0, option=0, excellent=0):
    info = game.item_info.get(between(group, 0, 15, 'group') * GROUP_SIZE + between(index, 0, GROUP_SIZE - 1, 'index'))
    if info is None:
        raise Refused('no item {} {}'.format(group, index))
    new = game.new_item(info, level=between(level, 0, 15, 'level'), skill=bool(has_skill), luck=bool(luck),
                        option=between(option, 0, 7, 'option'), excellent=between(excellent, 0, 0x3F, 'excellent'))
    slot = inventory.free_slot(c.player.inventory, info)
    if slot is None:
        raise Refused('no room for ' + info.name)
    c.player.inventory[slot] = new
    inventory.send(c)
    return '{} in slot {}'.format(new, slot)


def move(game, c, map_id, x, y):
    m = game.maps.get(map_id)
    if m is None:
        raise Refused('no map {}'.format(map_id))
    if not m.terrain.walkable(x, y):
        raise Refused('{},{} isn\'t walkable'.format(x, y))
    game.relocate(c, map_id, x, y, c.player.direction,
                  lambda p: SMapMove(map=p.map_id, x=p.x, y=p.y, direction=p.direction))
    return '{} {},{}'.format(m.name, x, y)


def learn(game, c, number):
    if number not in game.skills:
        raise Refused('no skill {}'.format(number))
    if not skill.learn(c, number):
        raise Refused('skill {} not learned'.format(number))
    return 'learned ' + game.skills[number].name


def heal(game, c):
    p = c.player
    p.life, p.mana = p.max_life, p.max_mana
    c.write(SLife(value=p.life))
    c.write(SMana(value=p.mana))
    return 'healed'


def pk_count(game, c, n):
    pk.set_count(game, c, between(n, pk.MIN_COUNT, pk.MAX_COUNT, 'pk count'))
    return 'pk count {}, level {}'.format(n, c.player.pk)


def devil_square_now(game, c):
    if not devil_square.start_now(game):
        raise Refused('Devil Square is open or running')
    return 'Devil Square is open'


COMMANDS = {'level': level, 'points': points, 'zen': zen, 'item': item, 'move': move, 'skill': learn, 'heal': heal,
            'pk': pk_count, 'ds': devil_square_now}
