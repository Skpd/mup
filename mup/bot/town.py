"""
Town trips (mup.bot.activity.Trip): what a bot does at the NPCs, from what a player knows: its own items and zen, the
game's data (the shops' goods, the smiths, the vault keepers, where they stand) and the client's prices
(mup.server.shop).

Errands: sell what it doesn't use (any shop), repair (the smiths), healing and mana potions, arrows and bolts for its
bow, an upgrade from a shop of its map, the vault for its jewels. Some make a trip due (out of potions, a piece worn
half, a full grid, an upgrade worth the walk), the others are done along with them in the town it goes to. The zen
goes to them in ORDER: what comes first is kept for when a later one buys. The numbers are mup's choices.
"""
import math
from dataclasses import dataclass, field
from typing import Optional, Set
from mup.bot import gear
from mup.model.item import GRID, Item
from mup.server import inventory, item as items, npc as npcs, shop
from mup.server.shop import Shop
from mup.server.world import distance

SELL, REPAIR, POTIONS, AMMO, UPGRADE, MANA, VAULT = ('sell', 'repair', 'potions', 'ammunition', 'upgrade', 'mana',
                                                     'vault')
ORDER = (REPAIR, POTIONS, AMMO, UPGRADE, MANA)  # what the zen goes to first
LOW = 2  # healing potions it goes to buy more below
MIN_HEAL = 0.2  # share of its life a healing potion it buys gives, when one does
REPAIR_DUE = 0.5  # durability share of a worn piece it goes to repair at: its values drop below half (0x45baf0)
REPAIR_ALONG = 0.9  # what is worn below this share is repaired along with other errands
FULL = 8  # free tiles of the grid under which selling or storing is due
SELL_DUE = 200  # zen its junk has to sell for to go sell it
UPGRADE_DUE = 0.05  # share an upgrade adds to make a trip for it, any along with other errands
STACKS = 4  # stacks of arrows or bolts it buys, of the best level of which 4 cost at most half its zen
AMMO_BELOW = 60  # arrows or bolts left it buys more below


@dataclass(frozen=True, eq=False)
class Npc:
    """An NPC bots go to: where it stands (the spawn's spot) and its shop, None for a vault keeper."""
    type_id: int
    map_id: int
    x: int
    y: int
    shop: Optional[Shop] = None

    def sells(self, test):
        """(slot, Item) of its goods that test(item) takes, by slot."""
        return [(slot, i) for slot, i in sorted(self.shop.items.items()) if test(i)] if self.shop is not None else []


def town_npcs(game):
    """[Npc] of the game: the shops and the vault keepers, in the order of their ids."""
    found = []
    for o in sorted(game.monsters.values(), key=lambda m: m.cid):
        if o.npc and (o.type_id in game.shops or o.type_id == npcs.VAULT_KEEPER):
            found.append(Npc(o.type_id, o.map_id, o.spawn.xs.start, o.spawn.ys.start, game.shops.get(o.type_id)))
    return found


def able(n, kind, detail=None):
    """NPC n does errand kind (detail: the ammunition type, the upgrade's Offer)."""
    if kind == VAULT:
        return n.type_id == npcs.VAULT_KEEPER
    if n.shop is None:
        return False
    if kind == SELL:
        return True
    if kind == REPAIR:
        return n.type_id in shop.REPAIRERS
    if kind == POTIONS:
        return bool(n.sells(lambda i: gear.potion_kind(i) == gear.HEALING))
    if kind == MANA:
        return bool(n.sells(lambda i: gear.potion_kind(i) == gear.MANA))
    if kind == AMMO:
        return bool(n.sells(lambda i: i.type == detail))
    if kind == UPGRADE:
        return n is detail.npc
    return False


@dataclass
class Offer:
    """An upgrade from a shop: the NPC, the slot of its goods, the item and its price, the share it adds."""
    npc: Npc
    slot: int
    item: Item
    price: int
    gain: float


@dataclass
class Stop:
    """An NPC of a trip and the errands it does there (selling at any shop on the way)."""
    npc: Npc
    errands: Set[str] = field(default_factory=set)


# what it carries

def junk(brain, keep=()):
    """[(slot, Item, price)] of its grid it sells: what it doesn't use and a shop pays for, but potions it drinks
    (those over its stock too) and the types in keep (the arrows a trip buys for a bow it buys)."""
    p = brain.player
    found = []
    for slot, item in sorted(p.inventory.items()):
        kind = gear.potion_kind(item)
        if kind == gear.HEALING or kind == gear.MANA and gear.uses_mana(brain.c.server, p) or item.type in keep:
            continue
        if slot >= GRID and brain.value(item, slot) <= 0:
            gold = gear.price(item)
            if gold > 0:
                found.append((slot, item, gold))
    return found


def worn(p, below=REPAIR_ALONG, equipment=False):
    """[(slot, Item)] of its inventory a smith repairs that are worn under below of their full durability, the
    equipment only with equipment."""
    return [(slot, i) for slot, i in sorted(p.inventory.items()) if (slot < GRID or not equipment)
            and shop.repairable(i) and i.durability < below * items.max_durability(i)]


def repair_cost(p, pieces=None):
    """What repairing pieces ([(slot, Item)]) costs at a smith's, None: everything worn at all, the repair of all
    (34 FF)."""
    return sum(shop.repair_cost(i, 0) for _, i in (worn(p, 1.0) if pieces is None else pieces))


def free_tiles(p):
    return inventory.INVENTORY.columns * inventory.INVENTORY.rows - len(inventory.taken(p.inventory))


def jewels(p):
    """[(slot, Item)] of the jewels in its grid, it keeps them in the vault."""
    return [(slot, i) for slot, i in sorted(p.inventory.items()) if slot >= GRID and i.type in gear.JEWELS]


def have(p, kind):
    return sum(i.durability for _, i in gear.potions(p, kind))


def potion_choice(p, goods, kind, potion_below, budget=None):
    """(slot, price, Item) of the potions of kind it buys from goods (slot -> Item): healing potions that give at
    least MIN_HEAL of its life first, of them the most life per zen of what it lacks when it drinks (below
    potion_below); mana potions the most mana per zen; stacks before single ones. Within budget when given. None."""
    lacks = p.max_life * (1 - potion_below)
    best = None
    for slot, item in sorted(goods.items()):
        if gear.potion_kind(item) != kind:
            continue
        gold = shop.value(item)
        if gold <= 0 or budget is not None and gold > budget:
            continue
        n = max(1, item.durability)
        if kind == gear.HEALING:
            gives = gear.heal(p, item)
            key = (gives >= MIN_HEAL * p.max_life, min(gives, lacks) * n / gold, n, -slot)
        else:
            key = (True, p.max_mana * items.MANA[item.type] // 100 * n / gold, n, -slot)
        if best is None or key > best[0]:
            best = key, slot, gold, item
    return best[1:] if best is not None else None


def ammo_choice(p, goods, ammo):
    """(slot, price, Item) of the stack of arrows or bolts (type ammo) it buys from goods: the best level of which
    STACKS cost at most half its zen, else the cheapest it can pay. None."""
    offers = [(i.level, shop.value(i), slot, i) for slot, i in sorted(goods.items()) if i.type == ammo]
    rich = [o for o in offers if o[1] * STACKS <= p.zen // 2]
    if rich:
        _, gold, slot, item = max(rich, key=lambda o: (o[0], -o[2]))
        return slot, gold, item
    cheap = [o for o in offers if o[1] <= p.zen]
    if not cheap:
        return None
    _, gold, slot, item = min(cheap, key=lambda o: (o[1], o[2]))
    return slot, gold, item


def ammunition(brain):
    """The type of the arrows or bolts it is short of: it has a bow or crossbow it may wear and would shoot with,
    fewer than AMMO_BELOW of them and the zen for a stack, a shop sells them on its map or one the gates lead to.
    None."""
    p = brain.player
    for slot, item in sorted(p.inventory.items()):
        ammo = gear.ammunition_for(item)
        if ammo is None or gear.shots(p, ammo[0]) >= AMMO_BELOW or not inventory.class_allowed(p, item.info):
            continue
        if not gear.meets(p, item):
            continue
        if slot >= GRID and brain.value(item, slot) <= 0:
            continue
        if p.zen < stack_price(brain, ammo[0]) or nearest(brain, [n for n in brain.c.manager.npcs
                                                                   if able(n, AMMO, ammo[0])]) is None:
            continue
        return ammo[0]
    return None


def stack_price(brain, ammo):
    """Zen a full stack of ammo +0 costs."""
    info = brain.c.server.item_info[ammo]
    return shop.value(Item(info, durability=info.durability))


# costs

def cost(brain, kind, detail=None):
    """Zen errand kind still takes from what it carries: the repair of everything worn, the potions it lacks of its
    stock, the stacks of arrows or bolts, the upgrade's price."""
    p, manager = brain.player, brain.c.manager
    if kind == REPAIR:
        return repair_cost(p)
    if kind in (POTIONS, MANA):
        potion = gear.HEALING if kind == POTIONS else gear.MANA
        lacks = gear.STOCK - have(p, potion)
        if lacks <= 0:
            return 0
        sellers = [n for n in manager.npcs if able(n, kind)]
        if not sellers:
            return 0
        choice = potion_choice(p, sellers[0].shop.items, potion, brain.personality.potion_below)
        if choice is None:
            return 0
        _, gold, item = choice
        return math.ceil(lacks / max(1, item.durability)) * gold
    if kind == AMMO:
        if detail is None:
            return 0
        stack = brain.c.server.item_info[detail].durability or 1
        return max(0, STACKS - gear.shots(p, detail) // stack) * stack_price(brain, detail)
    if kind == UPGRADE:
        return detail.price if detail is not None else 0
    return 0


def reserve(brain, errands, kind):
    """Zen it keeps for the errands that come before kind (ORDER)."""
    before = ORDER[:ORDER.index(kind)] if kind in ORDER else ORDER
    return sum(cost(brain, k, errands[k]) for k in before if k in errands)


# upgrades

def offer(brain, budget):
    """The best Offer of the shops of its map it can pay with budget: a piece it may wear now, weighed by the share it
    adds (mup.bot.gear.best_change, a bow with its arrows), the cheaper of the same worth. None."""
    c, p = brain.c, brain.player
    game = c.server
    best = None
    if not brain.types():
        return None  # it doesn't know yet what it hunts
    for n in c.manager.npcs:
        if n.map_id != p.map_id or n.shop is None:
            continue
        for slot, item in sorted(n.shop.items.items()):
            if not gear.slots_for(item) or item.type in inventory.AMMO or not inventory.class_allowed(p, item.info):
                continue
            gold = shop.value(item)
            if gold > budget or not gear.meets(p, item):
                continue
            change = gear.best_change(game, gear.armed(game, p, item), brain.types(), brain.personality.risk, item)
            if change is not None and (best is None or (change.gain, -gold) > (best.gain, -best.price)):
                best = Offer(n, slot, item, gold, change.gain)
    return best


# trips

def errands(brain, now):
    """(due, along): dicts errand -> detail (the ammunition type, the upgrade's Offer, True) of what makes a trip
    worth it now and of what it does along with it."""
    p = brain.player
    due, along = {}, {}
    sold = junk(brain)
    sales = sum(gold for _, _, gold in sold)
    zen = p.zen + sales
    if sold:
        along[SELL] = True
        if free_tiles(p) < FULL and sales >= SELL_DUE:
            due[SELL] = True
    if worn(p):
        along[REPAIR] = True
        pieces = worn(p, REPAIR_DUE, equipment=True)
        if pieces and repair_cost(p, pieces) <= zen:
            due[REPAIR] = True
    choice = cheapest_potion(brain, gear.HEALING)
    if have(p, gear.HEALING) < gear.STOCK and choice is not None and choice <= zen:
        along[POTIONS] = True
        if have(p, gear.HEALING) < LOW:
            due[POTIONS] = True
    choice = cheapest_potion(brain, gear.MANA)
    if gear.uses_mana(brain.c.server, p) and have(p, gear.MANA) < gear.STOCK and choice is not None \
            and choice <= zen:
        along[MANA] = True
    ammo = ammunition(brain)
    if ammo is not None:
        along[AMMO] = ammo
        if zen - reserve(brain, along, AMMO) >= stack_price(brain, ammo):
            due[AMMO] = ammo
    if jewels(p):
        along[VAULT] = True
        if free_tiles(p) < FULL:
            due[VAULT] = True
    o = brain.upgrade(now, zen - reserve(brain, along, UPGRADE))
    if o is not None and o.gain >= gear.UPGRADE:
        along[UPGRADE] = o
        if o.gain >= UPGRADE_DUE:
            due[UPGRADE] = o
        bow = gear.ammunition_for(o.item)
        if bow is not None and AMMO not in along and not any(i.type == bow[0] for i in p.inventory.values()):
            along[AMMO] = bow[0]
            if UPGRADE in due:
                due[AMMO] = bow[0]
    return due, along


def cheapest_potion(brain, kind):
    """Zen of the stack of potions of kind it would buy (potion_choice), None when no shop sells it."""
    sellers = [n for n in brain.c.manager.npcs if able(n, POTIONS if kind == gear.HEALING else MANA)]
    if not sellers:
        return None
    choice = potion_choice(brain.player, sellers[0].shop.items, kind, brain.personality.potion_below)
    return choice[1] if choice is not None else None


def nearest(brain, candidates, maps=None):
    """(Npc, steps) of the candidates nearest to it: of its map by the tiles from it, else of the maps the gates lead
    to by the steps of the route there; only those on maps when given. None."""
    p = brain.player
    if maps is not None:
        candidates = [n for n in candidates if n.map_id in maps]
    here = [(distance(n.x, n.y, p.x, p.y), i, n) for i, n in enumerate(candidates) if n.map_id == p.map_id]
    if here:
        d, _, n = min(here)
        return n, d
    if not candidates:
        return None
    steps = brain.map_steps()
    there = [(steps[n.map_id], i, n) for i, n in enumerate(candidates) if n.map_id in steps]
    if not there:
        return None
    d, _, n = min(there)
    return n, d


def plan(brain, due, along):
    """[Stop] of a trip for the due errands, with what is along done in the towns it goes to: each errand at a stop
    that does it, else at the NPC nearest to it that does (along: of a town of the trip). In the order it walks
    them, nearest first."""
    stops = []
    npcs_ = brain.c.manager.npcs
    for kinds, only_town in ((due, False), (along, True)):
        for kind in (UPGRADE, POTIONS, AMMO, REPAIR, VAULT, MANA, SELL):
            if kind not in kinds or any(kind in s.errands for s in stops):
                continue
            detail = kinds[kind]
            stop = next((s for s in stops if able(s.npc, kind, detail)), None)
            if stop is None:
                towns = {s.npc.map_id for s in stops} if only_town else None
                found = nearest(brain, [n for n in npcs_ if able(n, kind, detail)], towns)
                if found is None:
                    continue
                stop = next((s for s in stops if s.npc is found[0]), None)
                if stop is None:
                    stop = Stop(found[0])
                    stops.append(stop)
            stop.errands.add(kind)
    if SELL in along and not any(s.npc.shop is not None for s in stops) and stops:
        found = nearest(brain, [n for n in npcs_ if n.shop is not None], {s.npc.map_id for s in stops})
        if found is not None:
            stops.append(Stop(found[0], {SELL}))
    return ordered(brain, stops)


def ordered(brain, stops):
    """stops in the order it walks them: on its map the nearest next from where it stands, the others after in
    their order."""
    p = brain.player
    here = [s for s in stops if s.npc.map_id == p.map_id]
    rest = [s for s in stops if s.npc.map_id != p.map_id]
    result = []
    x, y = p.x, p.y
    while here:
        s = min(here, key=lambda s: (distance(s.npc.x, s.npc.y, x, y), s.npc.x, s.npc.y))
        here.remove(s)
        result.append(s)
        x, y = s.npc.x, s.npc.y
    return result + rest
