"""
Shops: the later server's Shop/*.txt and ShopManager.txt (data/shop), the items this client has, and the prices the
client shows (0x45ad50 and 0x486910, Prices in docs/protocol-097.md): buying, selling and repairing charge them.
"""
import logging
import math
import os
import struct
from dataclasses import dataclass, field
from typing import Dict
from mup.model.item import BOLT, ARROWS, GROUP_SIZE, GRID, Item
from mup.packet.server import SBuyResult, SDurability, SItemList, SPickUpResult, SRepairResult, SSellResult, STalk
from mup.server import inventory, item as items, skill, stats
from mup.server.ground import MAX_ZEN

logger = logging.getLogger(__name__)

BUY, SELL, REPAIR = 0, 1, 2  # the client's price kinds
REPAIRERS = {243, 246, 251}  # the client shows the repair buttons in their shops: Eo, Zienna, Hanzo
OWN_REPAIR_LEVEL = 80  # the inventory window has the repair button from this level
QUEST_ITEMS = range(14 * GROUP_SIZE + 23, 14 * GROUP_SIZE + 27)  # the client doesn't sell them

# what the client doesn't count by the item's formula
JEWEL_OF_BLESS, JEWEL_OF_SOUL, JEWEL_OF_LIFE = (14 * GROUP_SIZE + n for n in (13, 14, 16))
JEWEL_OF_CHAOS = 12 * GROUP_SIZE + 15
DEVILS_EYE, DEVILS_KEY, DEVILS_INVITATION = (14 * GROUP_SIZE + n for n in (17, 18, 19))
ALE = 14 * GROUP_SIZE + 9
FIXED_PRICES = {JEWEL_OF_BLESS: 100000, JEWEL_OF_SOUL: 70000, JEWEL_OF_CHAOS: 40000, 14 * GROUP_SIZE + 21: 9000,
                14 * GROUP_SIZE + 20: 900}
DEVIL_PRICES = {DEVILS_EYE: (30000, 15000, 21000, 30000, 45000), DEVILS_KEY: (30000, 15000, 21000, 30000, 45000),
                DEVILS_INVITATION: (120000, 60000, 84000, 120000, 180000)}
AMMUNITION_PRICES = {BOLT: (100, 1400, 2200), ARROWS: (70, 1200, 2000)}  # by level, a full stack
POTIONS = range(14 * GROUP_SIZE, 14 * GROUP_SIZE + 9)  # the price is per piece
LEVEL_PRICE = {5: 4, 6: 10, 7: 25, 8: 45, 9: 65, 10: 95, 11: 135}  # added to the price level of weapons and armor
# items whose wear the sell price and the repair don't count: pets, the ring of transform, ammunition
NOT_WORN = {13 * GROUP_SIZE + n for n in (0, 1, 2, 3, 10)} | {BOLT, ARROWS}
WINGS = range(12 * GROUP_SIZE, 12 * GROUP_SIZE + 3)

# option ids of the client's item lines (0x45a270), see Character values in docs/protocol-097.md
DAMAGE_OPTION, MAGIC_OPTION, BLOCK_OPTION, DEFENSE_OPTION, LUCK, RECOVERY = 0x3C, 0x3D, 0x3E, 0x3F, 0x40, 0x41
WEAPON_SKILL_IDS = range(0x12, 0x19)
EXCELLENT_IDS = range(0x42, 0x50)


def f32(value):
    """value as the client's float."""
    return struct.unpack('<f', struct.pack('<f', value))[0]


SELL_WEAR = f32(-0.6)  # the client's float constants
DEAD_REPAIR = f32(1.4)
OWN_REPAIR = f32(0.05)


@dataclass
class Shop:
    """An NPC's goods: slot of the 8 x 15 grid -> the item as it is sold."""
    npc_type: int
    name: str
    items: Dict[int, Item] = field(default_factory=dict)


def load(directory, item_info):
    """NPC type -> Shop, from directory/ShopManager.txt (index, NPC type) and directory/NNN - name.txt."""
    files = {}
    for name in os.listdir(directory):
        if name[:3].isdigit() and name.endswith('.txt'):
            files[int(name[:3])] = name
    shops = {}
    with open(os.path.join(directory, 'ShopManager.txt'), encoding='latin-1') as f:
        for line in f:
            v = line.split('//', 1)[0].split()
            if len(v) < 2 or v[0] == 'end':
                continue
            index, npc_type = int(v[0]), int(v[1])
            if index not in files:
                logger.warning('%s: no file for shop %s', directory, index)
                continue
            shops[npc_type] = _load_shop(os.path.join(directory, files[index]), npc_type, item_info)
    return shops


def _load_shop(path, npc_type, item_info):
    shop = Shop(npc_type, os.path.basename(path)[6:-4])
    missing = 0
    used = set()
    with open(path, encoding='latin-1') as f:
        for line in f:
            v = line.split('//', 1)[0].split()
            if len(v) < 8 or v[0] == 'end':
                continue
            # Section Type Level Dur Skill Luck Option Excellent
            group, index, level, durability, has_skill, luck, option, excellent = (int(x) for x in v[:8])
            info = item_info.get(group * GROUP_SIZE + index) if index < GROUP_SIZE else None
            # the client prices arrows and bolts above +2 with garbage (0x45ad50)
            if info is None or info.type in AMMUNITION_PRICES and level > 2:
                missing += 1
                continue
            new = Item(info, level=level, skill=bool(has_skill), luck=bool(luck), option=option, excellent=excellent)
            new.durability = durability or items.max_durability(new)
            slot = inventory.free_slot(shop.items, info, inventory.WAREHOUSE, used)
            if slot is None:
                logger.warning('%s: no room for %s', path, info.name)
                continue
            used |= inventory.tiles(slot, info, inventory.WAREHOUSE)
            shop.items[slot] = new
    if missing:
        logger.debug('%s: %s items not in this client left out', path, missing)
    return shop


def options(item):
    """(id, value) of the option lines the client lists for an item (0x45a270): its skill, luck, its option and
    the excellent options. The value matters for the option only."""
    t = item.type
    found = []
    if item.skill:
        classes = item.info.classes
        if classes[1] and t in skill.KNIGHT_WEAPON_SKILLS:
            found.append((skill.KNIGHT_WEAPON_SKILLS[t], 0))
        if classes[2] and 4 * GROUP_SIZE <= t < 5 * GROUP_SIZE and t not in AMMUNITION_PRICES:
            found.append((skill.TRIPLE_SHOT, 6))
        if classes[3] and t == 18:
            found.append((skill.SLASH, 0))
    if item.luck and (t < 12 * GROUP_SIZE and t not in AMMUNITION_PRICES or t in WINGS):
        found.append((LUCK, 0))
    o = item.option
    if o:
        if t < 5 * GROUP_SIZE and t not in AMMUNITION_PRICES:
            found.append((DAMAGE_OPTION, 4 * o))
        elif 5 * GROUP_SIZE <= t < 6 * GROUP_SIZE:
            found.append((MAGIC_OPTION, 4 * o))
        elif 6 * GROUP_SIZE <= t < 7 * GROUP_SIZE:
            found.append((BLOCK_OPTION, 5 * o))
        elif 7 * GROUP_SIZE <= t < 12 * GROUP_SIZE:
            found.append((DEFENSE_OPTION, 4 * o))
        elif 13 * GROUP_SIZE + 8 <= t < 14 * GROUP_SIZE or t == WINGS.start:
            found.append((RECOVERY, o))
        elif t == WINGS.start + 1:
            found.append((MAGIC_OPTION, 4 * o))
        elif t == WINGS.start + 2:
            found.append((DAMAGE_OPTION, 4 * o))
    if 6 * GROUP_SIZE <= t < 12 * GROUP_SIZE or t in (13 * GROUP_SIZE + 8, 13 * GROUP_SIZE + 9):
        found += [(0x42 + n, 0) for n in range(6) if item.excellent & 0x20 >> n]
    elif t < 6 * GROUP_SIZE or t in (13 * GROUP_SIZE + 12, 13 * GROUP_SIZE + 13):
        found += [(0x48 + n, 0) for n in range(6) if item.excellent & 0x20 >> n]
    return found


def value(item, kind=BUY):
    """The price the client shows for an item (0x45ad50): kind BUY in a shop, SELL to a shop (a third, less what is
    worn), REPAIR the base of the repair cost (a third)."""
    t, info, level = item.type, item.info, item.level
    found = options(item)
    rank = info.level + 3 * level + (25 if any(o in EXCELLENT_IDS for o, _ in found) else 0)
    if t in AMMUNITION_PRICES:
        # the stack's price by the count left, +3 isn't priced by the client (it reads garbage)
        gold = item.durability * AMMUNITION_PRICES[t][min(level, 2)] // info.durability if info.durability else 0
    elif t in FIXED_PRICES:
        gold = FIXED_PRICES[t]
    elif t in DEVIL_PRICES:
        gold = DEVIL_PRICES[t][min(level, 4)]
    elif t == ALE and level == 1:
        gold = 1000
    elif info.value:
        gold = info.value * info.value * 10 // 12
        if t in POTIONS:
            gold *= item.durability
    elif info.group in (12, 13, 15):
        gold = rank ** 3 + 100
        for o, v in found:
            if o == RECOVERY:
                gold *= v + 1
    else:
        rank += LEVEL_PRICE.get(level, 0)
        gold = (rank + 40) * rank * rank // 8 + 100
        if info.group <= 6 and not info.two_handed:
            gold = gold * 80 // 100
        for o, v in found:
            if o in WEAPON_SKILL_IDS:
                gold += int(gold * 1.5)
            elif o in (DAMAGE_OPTION, MAGIC_OPTION, DEFENSE_OPTION, BLOCK_OPTION):
                step = v // 5 if o == BLOCK_OPTION else v // 4
                gold += gold * {1: 6, 2: 14, 3: 28, 4: 56}.get(step, 0) // 10
            elif o == LUCK:
                gold += gold * 25 // 100
            elif o in EXCELLENT_IDS:
                gold *= 2
    if kind != BUY:
        gold //= 3
    if kind == SELL and t < 14 * GROUP_SIZE and t not in NOT_WORN and t not in WINGS:
        full = items.max_durability(item)
        if info.durability or info.magic_durability:  # the client divides by 0 for the others, mup counts no wear
            gold += int((1.0 - item.durability / full) * gold * SELL_WEAR)
    return rounded(gold)


def rounded(gold):
    """The client's rounding of prices: to 100 from 1000, to 10 from 100."""
    if gold >= 1000:
        return gold // 100 * 100
    if gold >= 100:
        return gold // 10 * 10
    return gold


def repairable(item):
    """The client repairs all but potions, jewels, scrolls (group 14 and up), pets, ammunition and the ring of
    transform, wings included."""
    return item.type < 14 * GROUP_SIZE and item.type not in NOT_WORN


def repair_cost(item, own):
    """What the client shows to repair an item (0x486910): 3 * value^0.75 * worn + 1, 1.4 times at durability 0,
    5% more from the inventory window (own). 0 when it isn't worn."""
    full = items.max_durability(item)
    gold = value(item, REPAIR)
    worn = f32(1.0 - item.durability / full)
    if worn <= 0:
        return 0
    root = math.sqrt(gold)
    cost = root * math.sqrt(root) * 3.0 * worn + 1.0  # in the client's order
    if item.durability <= 0:
        cost *= DEAD_REPAIR
    cost = int(cost * own * OWN_REPAIR + cost)
    return rounded(cost)


def open_shop(game, c, npc):
    """c's player talks to a shop NPC: its window and goods."""
    shop = game.shops[npc.type_id]
    c.write(STalk(window=STalk.SHOP))
    c.write(SItemList.of(SItemList.SHOP, shop.items))


def shop_of(game, c):
    """The Shop whose window c has open, None without one."""
    w = c.window
    return game.shops.get(w.npc.type_id) if w is not None and w.kind == STalk.SHOP else None


def buy(game, c, slot):
    """c's player buys the item in slot of the shop it talks to: its price, a free spot in the grid. The money goes
    out with 22 FE before 32."""
    p = c.player
    shop = shop_of(game, c)
    goods = shop.items.get(slot) if shop is not None else None
    if p.dead or goods is None:
        c.write(SBuyResult.failed())
        return False
    price = value(goods)
    target = inventory.free_slot(p.inventory, goods.info)
    if price > p.zen or target is None:
        logger.debug('%s can\'t buy %s for %s: %s zen, slot %s', p.name, goods, price, p.zen, target)
        c.write(SBuyResult.failed())
        return False
    new = game.new_item(goods.info, level=goods.level, durability=goods.durability, skill=goods.skill,
                        luck=goods.luck, option=goods.option, excellent=goods.excellent)
    p.zen -= price
    p.inventory[target] = new
    logger.info('%s buys %s for %s zen', p.name, new, price)
    c.write(SPickUpResult.zen(p.zen))
    c.write(SBuyResult(slot=target, item=new.encode()))
    return True


def sell(game, c, slot):
    """c's player sells the item of inventory slot to the shop it talks to, for the client's price. The item is
    gone, the money at most MAX_ZEN."""
    p = c.player
    item = p.inventory.get(slot)
    if p.dead or shop_of(game, c) is None or item is None or item.type in QUEST_ITEMS:
        c.write(SSellResult(result=0))
        return False
    price = value(item, SELL)
    del p.inventory[slot]
    if slot < GRID:
        inventory.look_changed(game, c, slot)
        stats.update(c)
        skill.update_weapon_skills(game, c)
    p.zen = min(MAX_ZEN, p.zen + price)
    logger.info('%s sells %s for %s zen', p.name, item, price)
    c.write(SSellResult(result=1, money=p.zen))
    return True


def repair(game, c, slot, own):
    """c's player repairs the item in inventory slot, or everything (FF): at the smith's (own 0) or from its
    inventory (own 1, from level 80, no window open). The durabilities go out with 2A, then 34 with the money."""
    p = c.player
    w = c.window
    if own:
        allowed = p.level >= OWN_REPAIR_LEVEL and w is None
    else:
        allowed = w is not None and w.kind == STalk.SHOP and w.npc.type_id in REPAIRERS
    if p.dead or not allowed or own and slot == 0xFF:
        logger.debug('%s may not repair here (own %s)', p.name, own)
        return False
    slots = sorted(p.inventory) if slot == 0xFF else [slot]
    worn = [(s, p.inventory[s]) for s in slots if s in p.inventory and repairable(p.inventory[s])
            and p.inventory[s].durability < items.max_durability(p.inventory[s])]
    cost = sum(repair_cost(item, own) for _, item in worn)
    if not worn or cost > p.zen:
        logger.debug('%s: nothing to repair or %s zen for %s', p.name, p.zen, cost)
        return False
    p.zen -= cost
    for s, item in worn:
        item.durability = items.max_durability(item)
        item.wear = 0
        c.write(SDurability(slot=s, durability=item.durability, unlock=0))
    logger.info('%s repairs %s items for %s zen', p.name, len(worn), cost)
    stats.update(c)
    c.write(SRepairResult(money=p.zen))
    return True
