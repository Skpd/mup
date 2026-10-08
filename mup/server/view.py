"""
What each client has in view. c.view holds the players (connections), monsters and ground items the client of c was
shown with 12 / 13 / 20 and not yet removed with 14 / 21, so nothing is shown twice or left behind. Players see each
other both ways.
"""
from mup.model.item import GroundItem
from mup.model.monster import Monster
from mup.packet.server import SClear, SMeetMonster, SMeetPlayer, SMove, SGroundItems, SGroundZen, SItemsGone
from mup.server.world import VIEW_RANGE, distance

CHUNK = 100  # entries per packet: 14 is a C1 packet, 125 cids at most


def _send(c, of, items):
    items = list(items)
    for i in range(0, len(items), CHUNK):
        c.write(of(items[i:i + CHUNK]))


def _is_player(o):
    return not isinstance(o, (Monster, GroundItem))


def show(c, objects, dropped=False):
    """Sends c what it doesn't have in view yet of objects. dropped: ground items fall to the ground."""
    new = [o for o in objects if o not in c.view]
    players = [o for o in new if _is_player(o)]
    monsters = [o for o in new if isinstance(o, Monster)]
    ground = [o for o in new if isinstance(o, GroundItem)]
    if players:
        _send(c, SMeetPlayer.of, [(o.cid, o.player) for o in players])
    if monsters:
        _send(c, SMeetMonster.of, monsters)
    items = [g for g in ground if g.item is not None]
    if items:
        _send(c, lambda chunk: SGroundItems.of(chunk, dropped), items)
    zen = [g for g in ground if g.item is None]
    if zen:
        _send(c, lambda chunk: SGroundZen.of(chunk, dropped), zen)
    c.view.update(new)


def hide(c, objects):
    """Removes objects from what c has in view."""
    gone = [o for o in objects if o in c.view]
    cids = [o.cid for o in gone if not isinstance(o, GroundItem)]
    if cids:
        _send(c, SClear.of, cids)
    items = [o.id for o in gone if isinstance(o, GroundItem)]
    if items:
        _send(c, SItemsGone.of, items)
    c.view.difference_update(gone)


def refresh(game, c):
    """
    After c moved, entered or respawned: shows c what came into view and removes what left it, and the same for the
    players who see c. Returns the players who saw c before and still do, they need the walk.
    """
    p = c.player
    m = game.maps[p.map_id]
    players = set(m.players.near(p.x, p.y, VIEW_RANGE))
    players.discard(c)
    seen = players | set(m.monsters.near(p.x, p.y, VIEW_RANGE)) | set(m.items.near(p.x, p.y, VIEW_RANGE))

    # corpses stay until they respawn (monster_removed) or are out of range
    gone = {o for o in c.view - seen
            if not (isinstance(o, Monster) and o.dead and distance(o.x, o.y, p.x, p.y) <= VIEW_RANGE)}
    hide(c, gone)
    for o in gone:
        if _is_player(o):
            hide(o, [c])

    stayed = {o for o in players if c in o.view}
    show(c, seen)
    for o in players - stayed:
        show(o, [c])
    return stayed


def forget(game, c):
    """c leaves the map or the game: it disappears for everyone who sees it. Its own view is emptied without
    packets for the objects, the client clears them itself (map change, respawn) or isn't in game anymore. Ground
    items get a 21, whether the client clears them on a map change isn't known."""
    for o in viewers(game, c):
        hide(o, [c])
    hide(c, [o for o in c.view if isinstance(o, GroundItem)])
    c.view.clear()


def viewers(game, obj):
    """Players that have obj (a connection, a monster or a ground item) in view."""
    where = obj.player if _is_player(obj) else obj
    m = game.maps[where.map_id]
    return [c for c in m.players.near(where.x, where.y, VIEW_RANGE + 1) if obj in c.view]


def monster_appeared(game, mob):
    """A monster spawned: shown to the players near it."""
    for c in game.maps[mob.map_id].players.near(mob.x, mob.y, VIEW_RANGE):
        show(c, [mob])


def monster_removed(game, mob):
    """A monster's corpse goes away (it respawns elsewhere)."""
    for c in viewers(game, mob):
        hide(c, [mob])


def monster_walks(game, mob):
    """A monster starts walking to mob.walk_target: the players who see it get the walk."""
    x, y = mob.walk_target
    move = SMove(cid=mob.cid, x=x, y=y, direction=mob.direction << 4)
    for c in viewers(game, mob):
        c.write(move)


def monster_moved(game, mob):
    """A monster took a step: players it came close to see it, the ones it left lose it."""
    for c in game.maps[mob.map_id].players.near(mob.x, mob.y, VIEW_RANGE + 1):
        p = c.player
        if distance(p.x, p.y, mob.x, mob.y) <= VIEW_RANGE:
            show(c, [mob])
        else:
            hide(c, [mob])


def item_appeared(game, g):
    """An item fell on the ground: shown to the players near it."""
    for c in game.maps[g.map_id].players.near(g.x, g.y, VIEW_RANGE):
        show(c, [g], dropped=True)


def item_removed(game, g):
    """An item on the ground was picked up or went away."""
    for c in viewers(game, g):
        hide(c, [g])
