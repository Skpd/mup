from mup.model.monster import Monster
from mup.packet.server import SDamage, SAnnouncement, SKill, SExp, SLevelUp


def hit_monster(proto, monster: Monster, dmg, dmg_type=0):
    """Damage from proto's player to a monster, with kill, exp and level up."""
    p = proto.player
    nearby = proto.server.get_players_within(p.map_id, p.x, p.y)

    monster.life -= dmg

    if monster.life > 0:
        for c in nearby:
            c.write(SDamage(monster.cid, dmg, dmg_type))
        return

    monster.dead = True

    # todo exp: mob.base * log(mob.level - proto.player.level, 5)
    exp = min(90, p.next_exp)
    p.exp += exp
    proto.write(SAnnouncement('{} of {}'.format(p.exp, p.next_exp)))
    proto.write(SExp(exp, monster.cid, dmg))  # shows the last hit to the killer instead of the damage packet
    if p.exp >= p.next_exp:
        p.level += 1
        p.exp = 0
        p.max_life += 10
        p.max_mana += 15
        proto.write(SLevelUp(p.level, 5, p.max_life, p.max_mana))

    for c in nearby:
        if c != proto:
            c.write(SDamage(monster.cid, dmg, dmg_type))
        c.write(SKill(monster.cid, proto.cid))
