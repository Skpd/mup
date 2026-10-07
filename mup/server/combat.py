from mup.model.monster import Monster
from mup.packet.server import SDamage, SAnnouncement, SKill, SExp, SLevelUp


def hit_monster(proto, monster: Monster, dmg, flags=0):
    """Damage from proto's player to a monster, with kill, exp and level up. flags: SDamage colour flags."""
    p = proto.player
    nearby = proto.server.get_players_within(p.map_id, p.x, p.y)

    monster.life -= dmg

    if monster.life > 0:
        for c in nearby:
            c.write(SDamage.of(monster.cid, dmg, flags))
        return

    monster.dead = True

    # todo exp: mob.base * log(mob.level - proto.player.level, 5)
    exp = min(int(90 * proto.server.config.exp_rate), p.next_exp)
    p.exp += exp
    proto.write(SAnnouncement(message='{} of {}'.format(p.exp, p.next_exp)))
    proto.write(SExp.of(monster.cid, exp, dmg))  # shows the last hit to the killer instead of the damage packet
    if p.exp >= p.next_exp:
        p.level += 1
        p.exp = 0
        p.max_life += 10
        p.max_mana += 15
        proto.write(SLevelUp(level=p.level, points=5, max_life=p.max_life, max_mana=p.max_mana))

    for c in nearby:
        if c != proto:
            c.write(SDamage.of(monster.cid, dmg, flags))
        c.write(SKill(cid=monster.cid, killer=proto.cid))
