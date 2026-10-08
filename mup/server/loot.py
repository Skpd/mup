"""
What monsters drop. Random drops by the rates of Monster.txt: an item when rand(ItemRate) < ITEM_CHANCE (times the
drop rate), else zen when rand(MoneyRate) < ZEN_CHANCE, the shape of the usual servers with mup's numbers. Fixed
drops per monster type from the item_drops file roll on top of that, each line on its own.
"""
import random
from collections import defaultdict, namedtuple
from mup.model.item import GROUP_SIZE, ZEN

ITEM_CHANCE = 10
ZEN_CHANCE = 10
LEVEL_BAND = 20  # monsters drop items with a drop level up to this much below their own
LEVEL_STEP = 10  # one item level per this many monster levels above the item's drop level
SKILL_CHANCE = 0.15
LUCK_CHANCE = 0.1
OPTION_CHANCES = ((2, 0.05), (1, 0.15))  # option, chance; mup's choices

FixedDrop = namedtuple('FixedDrop', 'type level count chance')


def load_fixed(path, item_info):
    """Monster type -> FixedDrops of the item_drops file, none without a path. Lines: monster type, item group,
    item index, item level, count (the durability, the amount for zen 14/15, 0: the item's own), chance in %."""
    drops = defaultdict(list)
    if not path:
        return {}
    with open(path, encoding='latin-1') as f:
        for n, line in enumerate(f, 1):
            v = line.split('//', 1)[0].split()
            if not v:
                continue
            monster, group, index, level, count = (int(x) for x in v[:5])
            t = group * GROUP_SIZE + index
            if t != ZEN and t not in item_info:
                raise ValueError('{}:{}: no item {} {}'.format(path, n, group, index))
            drops[monster].append(FixedDrop(t, level, count, float(v[5])))
    return dict(drops)


def roll(game, mob):
    """The loot of a monster game killed: Items and zen amounts."""
    loot = []
    for d in game.fixed_drops.get(mob.type_id, ()):
        if random.random() * 100 < d.chance:
            if d.type == ZEN:
                loot.append(d.count)
            else:
                info = game.item_info[d.type]
                loot.append(game.new_item(info, level=d.level, **({'durability': d.count} if d.count else {})))

    info = mob.info
    if info.item_rate and random.randrange(info.item_rate) < ITEM_CHANCE * game.config.drop_rate:
        item = random_item(game, info)
        if item is not None:
            loot.append(item)
    elif info.money_rate and random.randrange(info.money_rate) < ZEN_CHANCE:
        loot.append(zen(info.level))
    return loot


def random_item(game, monster):
    """An item for a monster of type monster: one that drops with a drop level up to the monster's."""
    candidates = [i for i in game.item_info.values()
                  if i.drops and i.type != ZEN and monster.level - LEVEL_BAND <= i.level <= monster.level]
    if not candidates:
        return None
    info = random.choice(candidates)
    values = {}
    if info.group <= 11:
        values['level'] = random.randint(0, min(monster.max_item_level, (monster.level - info.level) // LEVEL_STEP))
    if info.skill:
        values['skill'] = random.random() < SKILL_CHANCE
    if info.options:
        values['luck'] = random.random() < LUCK_CHANCE
        values['option'] = next((o for o, chance in OPTION_CHANCES if random.random() < chance), 0)
    return game.new_item(info, **values)


def zen(level):
    """Zen a monster of a level drops, mup's choice."""
    base = level * level // 2 + 5 * level
    return max(1, random.randint(base * 3 // 4, base * 5 // 4))
