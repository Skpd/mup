import logging
import random
from mup.model.item import RIGHT_HAND, LEFT_HAND, HELM, ARMOR, PANTS, GLOVES, BOOTS, ARROWS, BOLT
from mup.model.monster import Monster
from mup.packet.server import SDamage, SKill, SLife, SMana, SRespawn, SDurability, SItemDeleted
from mup.server import effect, experience, ground, inventory, item as items, loot, monster, stats, summon, view
from mup.server.character import respawn_gate

logger = logging.getLogger(__name__)

RESPAWN_DELAY = 3.0  # seconds a dead player lies before it comes back in town
REGEN_INTERVAL = 3.0  # seconds between life and mana regeneration
LIFE_REGEN = 0.01  # of the maximum per interval, at least 1. mup's own rates
MANA_REGEN = 0.03
MIN_HIT_CHANCE = 5  # % of hits with an attack rate below the defense rate, usual 0.97 rule
EXCELLENT_DAMAGE = 120  # % of the max damage, usual
DUAL_WIELD = 55  # % of each hand's damage with two weapons, the client's window
MELEE_REACH = 3  # tiles, mup's choice: a step of lag over the client's reach
BOW_REACH = 8
ATTACK_INTERVAL = 0.4  # seconds per attack at speed 0, see paced()
ATTACK_BURST = 4
# wear an item takes before it loses a durability point (mup.server.item.wear): weapons by the defense of what they
# hit, armor by the damage taken. The later WebZen servers' shape, mup's numbers
WEAPON_WEAR, BOW_WEAR, STAFF_WEAR, ARMOR_WEAR = 564, 780, 1050, 69
ARMOR_SLOTS = (LEFT_HAND, HELM, ARMOR, PANTS, GLOVES, BOOTS)  # one of them takes a hit, the left hand with a shield


def hit_monster(proto, mob: Monster, dmg, flags=0, magic=False):
    """
    Damage from proto's player to a monster, with kill, exp, level up and loot. flags: SDamage colour flags. magic:
    a skill hit, the killer's hero doesn't swing at it (16).
    """
    game = proto.server
    nearby = view.viewers(game, mob)

    mob.damage_by[proto] = mob.damage_by.get(proto, 0) + min(dmg, mob.life)
    mob.life -= dmg

    if mob.life > 0:
        for c in nearby:
            c.write(SDamage.of(mob.cid, dmg, flags))
        return

    monster.kill(game, mob, game.now)
    # who gets exp sees the last hit in 16 instead of the damage packet
    rewarded = experience.reward_kill(game, mob, proto, dmg, magic)
    for c in nearby:
        if c not in rewarded:
            c.write(SDamage.of(mob.cid, dmg, flags))
        c.write(SKill(cid=mob.cid, killer=proto.cid))
    after_kill(proto)
    v = proto.player.values
    drops = [thing + thing * v.zen_bonus // 100 if isinstance(thing, int) else thing for thing in loot.roll(game, mob)]
    ground.drop_loot(game, mob.map_id, mob.x, mob.y, drops, proto)


def after_kill(c):
    """The killer's excellent options: + max life / 8 and + max mana / 8 for each."""
    p = c.player
    v = p.values
    if v.life_after_kill and p.life < p.max_life:
        p.life = min(p.max_life, p.life + v.life_after_kill * p.max_life // 8)
        c.write(SLife(value=p.life))
    if v.mana_after_kill and p.mana < p.max_mana:
        p.mana = min(p.max_mana, p.mana + v.mana_after_kill * p.max_mana // 8)
        c.write(SMana(value=p.mana))


def hit_check(attack_rate, defense_rate, rng=random):
    """The usual 0.97 miss check: an attack rate below the defense rate hits 5% of the time, otherwise it misses when
    a roll below the attack rate is below the defense rate."""
    if attack_rate < defense_rate:
        return rng.randrange(100) < MIN_HIT_CHANCE
    return attack_rate <= 0 or rng.randrange(attack_rate) >= defense_rate


def minimum_damage(level):
    """What a hit does at least when the defense takes all of it, mup's choice."""
    return max(1, level // 10)


def roll(v, ranges, rng=random):
    """Damage before defense from the (min, max) ranges of the hands that hit, each counting share %, and the
    colour flags: excellent (the option's chance) hits for 120% of the max, critical (luck) for the max."""
    if v.excellent_rate and rng.randrange(100) < v.excellent_rate:
        return sum(hi * EXCELLENT_DAMAGE // 100 * share // 100 for lo, hi, share in ranges), SDamage.EXCELLENT
    if v.critical_rate and rng.randrange(100) < v.critical_rate:
        return sum(hi * share // 100 for lo, hi, share in ranges), SDamage.CRITICAL
    return sum(rng.randint(lo, max(lo, hi)) * share // 100 for lo, hi, share in ranges), 0


def weapon_ranges(p):
    """(min, max, share %) of the hands a normal attack hits with, as the client's window shows the damage: the left
    hand with a bow (no crossbow in the right) or an empty right hand, knights and gladiators with a weapon in each
    hand both at 55%."""
    v = p.values
    right, left = p.inventory.get(RIGHT_HAND), p.inventory.get(LEFT_HAND)
    if stats.class_number(p) in (stats.DK, stats.MG) and right is not None and left is not None \
            and right.type < stats.SHIELDS.start and left.type < stats.SHIELDS.start:
        return [(v.damage_min, v.damage_max, DUAL_WIELD), (v.left_min, v.left_max, DUAL_WIELD)]
    if right is None or left is not None and left.type in stats.LEFT_BOWS and right.type not in stats.RIGHT_BOWS:
        return [(v.left_min, v.left_max, 100)]
    return [(v.damage_min, v.damage_max, 100)]


def ammunition(p):
    """The slot of the arrows / bolts a bow / crossbow in hand shoots, None for other weapons. False when a bow has
    none."""
    right, left = p.inventory.get(RIGHT_HAND), p.inventory.get(LEFT_HAND)
    if left is not None and left.type in stats.LEFT_BOWS:
        return RIGHT_HAND if right is not None and right.type == ARROWS and right.durability > 0 else False
    if right is not None and right.type in stats.RIGHT_BOWS:
        return LEFT_HAND if left is not None and left.type == BOLT and left.durability > 0 else False
    return None


def use_ammunition(game, c, slot):
    """One arrow / bolt of the stack in slot is shot: the count (2A), the stack gone at 0 (28, others see the look)."""
    p = c.player
    ammo = p.inventory[slot]
    ammo.durability -= 1
    if ammo.durability > 0:
        c.write(SDurability(slot=slot, durability=ammo.durability, unlock=0))
        return
    del p.inventory[slot]
    c.write(SItemDeleted(slot=slot, unlock=0))
    inventory.look_changed(game, c, slot)
    stats.update(c)


def worn_weapon(p, magic):
    """The slot of the weapon a hit wears: the staff for a wizard's skill, else the bow / crossbow or the weapon in
    hand (right first). None without one."""
    right, left = p.inventory.get(RIGHT_HAND), p.inventory.get(LEFT_HAND)
    if magic:
        return RIGHT_HAND if right is not None and right.type in stats.STAFFS else None
    if left is not None and left.type in stats.LEFT_BOWS:
        return LEFT_HAND
    for slot, item in ((RIGHT_HAND, right), (LEFT_HAND, left)):
        if item is not None and item.type < stats.SHIELDS.start and item.type not in (BOLT, ARROWS):
            return slot
    return None


def wear_weapon(c, mob, magic=False):
    """c's player hit mob: its weapon wears by the monster's defense."""
    p = c.player
    slot = worn_weapon(p, magic)
    if slot is None:
        return
    weapon = p.inventory[slot]
    damage_min = weapon.info.damage_min
    if not damage_min:
        return
    limit = STAFF_WEAR if magic else BOW_WEAR if weapon.info.group == 4 else WEAPON_WEAR
    if items.wear(weapon, mob.info.defense * 2 // (damage_min + damage_min // 2), limit):
        durability_lost(c, slot)


def wear_armor(c, dmg, rng=random):
    """c's player took a hit of dmg: a random piece of its armor (or its shield) wears by it."""
    p = c.player
    slot = rng.choice(ARMOR_SLOTS)
    piece = p.inventory.get(slot)
    if piece is None or slot == LEFT_HAND and piece.type not in stats.SHIELDS or not piece.info.defense:
        return
    if items.wear(piece, dmg * 2 // (piece.info.defense + piece.info.defense // 2), ARMOR_WEAR):
        durability_lost(c, slot)


def durability_lost(c, slot):
    """The item in slot lost a durability point: 2A tells the client, the values follow the wear (nothing from it at
    0)."""
    item = c.player.inventory[slot]
    c.write(SDurability(slot=slot, durability=item.durability, unlock=0))
    stats.update(c)


def reach(p):
    """Tiles a normal attack reaches, with some lag allowed, mup's choice."""
    return BOW_REACH if ammunition(p) is not None else MELEE_REACH


def paced(p, now, speed):
    """
    p may attack now at its attack / magic speed: each attack takes ATTACK_INTERVAL shortened by the speed, up to
    ATTACK_BURST may come at once (lag). The client's own pace isn't known, these are mup's numbers.
    """
    interval = ATTACK_INTERVAL / (1 + speed / 100)
    due = max(p.next_attack_at, now)
    if due - now > ATTACK_BURST * interval:
        return False
    p.next_attack_at = due + interval
    return True


def player_attack(game, c, mob, rng=random):
    """c's player hits mob with its weapon (15 request): miss check, damage, ammunition."""
    p = c.player
    slot = ammunition(p)
    if slot is False:
        logger.debug('%s has no ammunition', p.name)
        return
    if slot is not None:
        use_ammunition(game, c, slot)
    v = p.values
    if not hit_check(v.attack_rate, mob.info.defense_rate, rng):
        hit_monster(c, mob, 0)
        return
    dmg, flags = roll(v, weapon_ranges(p), rng)
    dmg += effect.value(c, effect.GREATER_DAMAGE)
    wear_weapon(c, mob)
    hit_monster(c, mob, max(dmg - mob.info.defense, minimum_damage(p.level)), flags)


def monster_attack(game, mob: Monster, c, rng=random):
    """mob hits the player of connection c: miss check, its damage less the defense and the damage decrease, the
    reflected part back to it."""
    v = c.player.values
    if not hit_check(mob.info.attack_rate, v.defense_rate, rng):
        c.write(SDamage.of(c.cid, 0))
        return
    defense = v.defense + effect.value(c, effect.GREATER_DEFENSE)
    dmg = max(rng.randint(mob.info.damage_min, mob.info.damage_max) - defense, minimum_damage(mob.info.level))
    dmg -= dmg * v.damage_decrease // 100
    if effect.has(c, effect.DEFENSE):
        dmg = max(1, dmg // 2)
    wear_armor(c, dmg, rng)
    hit_player(game, mob, c, dmg)
    reflected = dmg * v.reflect // 100
    if reflected > 0 and not mob.dead and not c.player.dead:
        hit_monster(c, mob, reflected)


def hit_player(game, mob: Monster, c, dmg):
    """A monster's hit on the player of connection c."""
    p = c.player
    p.life = max(0, p.life - dmg)
    # the client takes the damage off the life it shows, the life packet keeps both in step
    c.write(SDamage.of(c.cid, dmg))
    c.write(SLife(value=p.life))
    if p.life == 0:
        logger.info('%s was killed by %s %s', p.name, mob.info.name, mob.cid)
        kill_player(game, c, mob.cid)


def kill_player(game, c, killer):
    """The player of c died, killer: cid of who killed it."""
    p = c.player
    p.life = 0
    p.respawn_at = game.now + RESPAWN_DELAY
    effect.clear(game, c)
    summon.dismiss(game, c)
    experience.death_loss(p)
    kill = SKill(cid=c.cid, killer=killer)
    c.write(kill)
    for o in view.viewers(game, c):
        o.write(kill)


def respawn(game, c):
    """A dead player comes back with full life in the town of its map."""
    p = c.player
    p.life = p.max_life
    p.mana = p.max_mana
    p.respawn_at = None
    map_id, x, y = game.gate_spot(respawn_gate(p.map_id))
    game.relocate(c, map_id, x, y, 0, SRespawn.of)


def regen(c):
    p = c.player
    if p.dead:
        return
    if p.life < p.max_life:
        regen = max(1, int(p.max_life * LIFE_REGEN)) + p.max_life * p.values.life_recovery // 100
        p.life = min(p.max_life, p.life + regen)
        c.write(SLife(value=p.life))
    if p.mana < p.max_mana:
        p.mana = min(p.max_mana, p.mana + max(1, int(p.max_mana * MANA_REGEN)))
        c.write(SMana(value=p.mana))
