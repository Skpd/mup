"""
Fast tests: the game in process (mup.sim) on its own clock, no sockets and no waiting, the same game from the same
seed. Game time that tests/client.py waits for passes here as fast as the ticks run. The test world (monsters, NPCs,
drops, mixes) is tests/client.py's. Checks read the packets' values, the raw offsets are tests/client.py's job.

Bots (mup.bot) are checked here too: the session, the motor through a gate, the career's picks on the real data,
the brain's scenarios with the test monsters, four classes levelling, a bot's scenario played on; none may break the
client's rules (the fair play checker).

usage: ./venv/bin/python tests/sim.py
Exits non zero on the first failed check. tests/sim.py --digest SEED prints the digest of a run of hunters and bots
(the repeatable check runs it under another PYTHONHASHSEED).
"""
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from client import (MONSTERS, SPAWNS, DROPS, MIXES, ROOT, SPIDER_SPOT, HOUND_SPOT, B_SPOT, CHARON, DS_DRAGON,
                    check)  # noqa: E402 (client puts the repository on the path)
from mup.bot import CLASSES, career, motor
from mup.bot.activity import Hunt, Rest
from mup.model.monster import Monster
from mup.model.player import CharacterClass
from mup.packet.client import CAttack, CDevilSquareEnter, CMove, CPickUp, CTalk
from mup.packet.server import (SClear, SDevilSquareRanking, SDevilSquareResult, SGroundItems, SGroundZen, SItemsGone,
                               SKill, SLife, SMapMove, SMeetMonster, SMeetPlayer, SMove, SPickUpResult, SRespawn)
from mup.server import combat, command, devil_square, ground, monster
from mup.server.game import TICK
from mup.server.world import distance
from mup.sim import Sim, Hunter, of

SWING = 0x64
# test monster spawns for bots: the spider alone, and the spider north of a wall at Lorencia's north (124,50 and
# 124,52 are 2 tiles apart, the walk around takes 70 steps)
SPIDER_ONLY = """
2
003 00 30 {} {} -1
end
""".format(*SPIDER_SPOT)
WALL = (124, 50), (124, 52)
WALL_SPIDER = """
2
003 00 30 {} {} -1
end
""".format(*WALL[1])


def world(tmp, spawns=SPAWNS, name='monster_spawns'):
    """Config of tests/client.py's test world, its files written to tmp. spawns: another MonsterSetBase text, name:
    its file's."""
    files = {}
    for key, file, text in (('monster_info', 'monster_info', MONSTERS), ('monster_spawns', name, spawns),
                            ('item_drops', 'item_drops', DROPS), ('mixes', 'mixes', MIXES)):
        files[key] = os.path.join(tmp, file + '.txt')
        Path(files[key]).write_text(text)
    return dict(files, devil_square_times='', devil_square_entry=2.0, devil_square_length=6.0,
                devil_square_close=2.0)


def free_tile(sim, map_id, spot, at_least, at_most):
    """A walkable tile outside the safe zone between at_least and at_most tiles from spot, the first row by row."""
    t = sim.game.maps[map_id].terrain
    x0, y0 = spot
    for y in range(y0 - at_most, y0 + at_most + 1):
        for x in range(x0 - at_most, x0 + at_most + 1):
            if at_least <= distance(x, y, x0, y0) and t.walkable(x, y) and not t.safe(x, y):
                return x, y
    raise AssertionError('no free tile near {}'.format(spot))


def monster_of(c, type_id):
    """A living monster of type_id in c's view."""
    found = [o for o in c.view if isinstance(o, Monster) and o.type_id == type_id and not o.dead]
    if not found:
        raise AssertionError('no monster {} in view of {}'.format(type_id, c))
    return found[0]


def listed(cls, key, value):
    """Predicate: a list packet of class cls with an entry whose key is value."""
    return lambda p: isinstance(p, cls) and any(e[key] == value for e in p.entries)


def swing_until_dead(c, mob, limit=60.0):
    """c swings at mob every 0.4 s until its 17. Returns the game time it died."""
    sim = c.sim
    end = sim.now + limit
    while sim.now < end:
        c.send(CAttack(attacked_cid=mob.cid, action=SWING, direction=0))
        if any(of(SKill, cid=mob.cid)(p) for p in c.inbox):  # the handler kills it at once
            c.recv_until(of(SKill, cid=mob.cid))
            return sim.now
        sim.run(0.4)
    raise AssertionError('{} did not kill {} within {} game seconds'.format(c, mob.cid, limit))


def hunt_digest(seed, minutes=3):
    """Digest of 4 hunters hunting outside Lorencia and 2 bots for minutes on the real data."""
    with Sim(seed=seed) as sim:
        for i in range(4):
            sim.enter('Hunter{}'.format(i), at=(0, 180 + i, 127), cls=Hunter)
        sim.bot('BotDk', CharacterClass.DARK_KNIGHT)
        sim.bot('BotDw', CharacterClass.DARK_WIZARD)
        sim.run(minutes * 60)
        return sim.digest()


def repeatable():
    print('the same seed, the same game (hunters and bots)')
    first = hunt_digest(1)
    check(hunt_digest(1) == first, 'hunters with seed 1 twice: one digest ' + first[:12])
    other = subprocess.run([sys.executable, __file__, '--digest', '1'], capture_output=True, text=True,
                           env={**os.environ, 'PYTHONHASHSEED': '12345'}, cwd=ROOT)
    check(other.stdout.strip() == first, 'and in another process with another PYTHONHASHSEED: ' +
          (other.stdout.strip()[:12] or other.stderr[-300:]))
    check(hunt_digest(2) != first, 'seed 2 is another game')


def walking(cfg):
    print('walking')
    with Sim(**cfg) as sim:
        x, y = B_SPOT
        a = sim.enter('Alice', at=(0, x, y))
        b = sim.enter('Bobby', at=(0, x - 2, y))
        a.send(CMove.of(x, y, [3, 3, 3]))
        p = b.recv_until(of(SMove, cid=a.cid), what='the walk')
        check((p.x, p.y, p.direction) == (x + 3, y, 3 << 4), 'B sees A walk 3 tiles east, facing east')
        check((a.player.x, a.player.y) == (x + 3, y), 'the server has A at the end of the walk')


def dying(cfg):
    print('a hound kills, the player is back in town 3 s later')
    with Sim(**cfg) as sim:
        a = sim.enter('Alice', at=(0, *free_tile(sim, 0, HOUND_SPOT, 4, 5)))
        a.recv_until(of(SKill, cid=a.cid), limit=30, what='A killed')
        died = sim.now
        p = a.recv_until(lambda p: isinstance(p, SRespawn), limit=5, what='respawn')
        check(abs(sim.now - died - combat.RESPAWN_DELAY) <= TICK,
              'F3 04 {:.1f} game seconds after 17'.format(sim.now - died))
        player = a.player
        check(p.map == 0 and sim.game.maps[0].terrain.safe(p.x, p.y), 'in Lorencia\'s town')
        check(player.life == player.max_life == p.life, 'with full life')


def monster_respawn(cfg):
    print('a killed spider comes back after its regen time')
    with Sim(**cfg) as sim:
        a = sim.enter('Alice', at=(0, *free_tile(sim, 0, SPIDER_SPOT, 4, 5)))
        spider = monster_of(a, 3)
        command.move(sim.game, a, 0, *free_tile(sim, 0, (spider.x, spider.y), 1, 1))
        died = swing_until_dead(a, spider)
        a.inbox.clear()  # the move showed it already
        a.recv_until(listed(SMeetMonster, 'cid', spider.cid), limit=30, what='spider back')
        check(abs(sim.now - died - spider.info.regen_time) <= TICK,
              'back in view {:.1f} game seconds after its 17, regen time {}'.format(sim.now - died,
                                                                                     spider.info.regen_time))


def drops(cfg):
    print('drops: the killer\'s for 10 s, gone after 60 s')
    with Sim(**cfg) as sim:
        a = sim.enter('Alice', at=(0, *free_tile(sim, 0, SPIDER_SPOT, 4, 5)))
        spider = monster_of(a, 3)
        next_to = free_tile(sim, 0, (spider.x, spider.y), 1, 1)
        command.move(sim.game, a, 0, *next_to)
        b = sim.enter('Bobby', at=(0, *next_to))
        dropped = swing_until_dead(a, spider)
        z = b.recv_until(lambda p: isinstance(p, SGroundZen), what='zen on the ground').entries[0]
        items = [e for _ in range(2) for e in b.recv_until(lambda p: isinstance(p, SGroundItems),
                                                           what='items on the ground').entries]
        check(len(items) == 2, 'the spider leaves 2 items and zen')
        zen_id = z['id'] & 0x7FFF
        b.send(CPickUp(id=zen_id))
        p = b.recv_until(lambda p: isinstance(p, SPickUpResult))
        check(p.slot == SPickUpResult.FAILED, 'B can\'t pick up the zen at once')
        sim.run_until(lambda: sim.now >= dropped + ground.OWNER_TIME, what='owner time over')
        b.send(CPickUp(id=zen_id))
        p = b.recv_until(lambda p: isinstance(p, SPickUpResult))
        check(p.slot == SPickUpResult.ZEN and b.player.zen == 30, 'after 10 game seconds he can: 30 zen')
        item_id = items[0]['id'] & 0x7FFF
        a.recv_until(listed(SItemsGone, 'id', item_id), limit=ground.LIFETIME + 1, what='item gone')
        check(abs(sim.now - dropped - ground.LIFETIME) <= TICK,
              'the items lie {:.1f} game seconds'.format(sim.now - dropped))


def regeneration(cfg):
    print('regeneration')
    with Sim(**cfg) as sim:
        a = sim.enter('Alice', at=(0, *B_SPOT))
        a.player.life = 10
        a.inbox.clear()
        took = sim.run_until(lambda: any(isinstance(p, SLife) and p.value > 10 for p in a.inbox),
                             limit=combat.REGEN_INTERVAL + 1, what='life back')
        check(took <= combat.REGEN_INTERVAL + TICK, 'life comes back within {:.1f} game seconds'.format(took))


def devil_square_round(cfg):
    print('a Devil Square round, entry to ranking')
    with Sim(**cfg) as sim:
        game = sim.game
        b = sim.enter('Bobby', at=(0, CHARON[1][0], CHARON[1][1] + 2), level=150)
        command.item(game, b, 14, 19, level=2)
        slot = next(s for s, i in b.player.inventory.items() if i.type == 14 * 32 + 19)
        charon = monster_of(b, CHARON[0])
        b.inbox.clear()  # the level's F3 04 in Lorencia
        command.devil_square_now(game, b)
        b.send(CTalk(cid=charon.cid))
        b.send(CDevilSquareEnter(square=1, slot=slot + 12))
        check(b.recv_until(lambda p: isinstance(p, SDevilSquareResult)).result == 0, 'B enters the second square')
        check(b.recv_until(lambda p: isinstance(p, SMapMove)).map == devil_square.MAP, 'and is in Devil Square')
        command.move(game, b, devil_square.MAP, DS_DRAGON[0] - 1, DS_DRAGON[1])
        b.recv_until(listed(SMeetMonster, 'type', 2), limit=10, what='the dragon')
        swing_until_dead(b, monster_of(b, 2))
        check(True, 'the round starts, B kills the square\'s dragon')
        p = b.recv_until(lambda p: isinstance(p, SDevilSquareRanking), limit=10, what='ranking')
        check(p.rank == 1 and p.entries[0]['name'] == 'Bobby', 'the ranking: B first')
        p = b.recv_until(lambda p: isinstance(p, SRespawn), limit=5, what='back to Noria')
        check(p.map == 3, 'then back to Noria')


def around(c):
    """cid -> x, y, life of the living monsters in c's view."""
    return {m.cid: (m.x, m.y, m.life) for m in c.view if isinstance(m, Monster) and m.attackable and not m.dead}


def scenario(tmp):
    print('a scenario: dumped, loaded, played on')
    path = os.path.join(tmp, 'hunter.json')
    with Sim(seed=5) as sim:
        h = sim.enter('Hunter', at=(0, 180, 127), cls=Hunter)
        command.item(sim.game, h, 0, 1)
        sim.run(120)
        sim.run_until(lambda: len(around(h)) >= 3, limit=600, what='monsters around')
        sim.dump(h, path)
        dumped = sim.now
        p = h.player
        saved = p.level, p.exp, p.map_id, p.x, p.y, p.life, sorted((s, i.type) for s, i in p.inventory.items())
        near = around(h)
    sim, h = Sim.load(path, Hunter)
    with sim:
        p = h.player
        check(sim.now == dumped and (p.level, p.exp, p.map_id, p.x, p.y, p.life,
                                     sorted((s, i.type) for s, i in p.inventory.items())) == saved,
              'the character as it was at game time {:.1f}: level {}, {} exp, {},{}'.format(
                  dumped, p.level, p.exp, p.x, p.y))
        check(around(h) == near, 'the {} monsters around it where they were, with their life'.format(len(near)))
        sim.run(60)
        check(h.player.exp > saved[1] or h.player.level > saved[0], 'it plays on: {} exp a minute later'.format(
            h.player.exp))


def fair(*bots):
    """The bots broke none of the client's rules and the server refused them nothing."""
    for c in bots:
        check(not c.checker.errors and not c.counts['refused'], '{}: no fair play errors, nothing refused ({})'.format(
            c.bot.name, c.checker.errors[:3] or c.counts['refused']))


def traced(sim):
    """The bots' events of sim, as a list that fills while it runs."""
    events = []
    sim.bots.trace = events.append
    return events


def bot_session(cfg):
    print('a bot logs in and out like a client')
    with Sim(**cfg) as sim:
        a = sim.enter('Alice', at=(0, 140, 125))
        c = sim.bot('Botty', at=(0, 142, 125))
        p = a.recv_until(listed(SMeetPlayer, 'cid', c.cid), what='the bot in view')
        check(next(e for e in p.entries if e['cid'] == c.cid)['name'] == 'Botty', 'A gets 12 with the bot, Botty')
        sim.run(5)
        check(c.brain.ground is not None, 'it picked a ground to hunt on')
        sim.bots.logout(c)
        a.recv_until(listed(SClear, 'cid', c.cid), what='the bot gone')
        check(True, 'A gets 14 when it logs out')
        row = sim.bots.store.load('Botty')
        check(row.career.get('ground') == list(c.brain.ground.key), 'its row is saved with its ground: {}'.format(
            row.career))
        check(not sim.game.accounts.load('Botty').password_hash.startswith('scrypt'), 'its account has no password')


def bot_motor(cfg):
    print('the motor: to the Noria gate at the client\'s pace, through it from level 10')
    with Sim(**cfg) as sim:
        game = sim.game
        c = sim.bot('Walker', at=(0, 140, 125), brain=False)
        p = c.player
        field = c.manager.flows.gate(23)
        steps = field.distance(p.x, p.y)
        start = sim.now
        c.motor.follow(field)
        sim.run_until(lambda: c.motor.blocked_gate == 23, limit=steps * motor.STEP_TIME + 30, what='at the gate')
        took = sim.now - start
        check(abs(took - steps * motor.STEP_TIME) <= 2, '{} steps in {:.1f} game seconds, {} s a tile'.format(
            steps, took, motor.STEP_TIME))
        check(p.map_id == 0 and c.sent['MoveGate'] == 0, 'level 1 on gate 23: no 1C, as the client (level 10 needed)')
        command.level(game, c, 10)
        sim.run_until(lambda: p.map_id == 3, limit=5, what='through the gate')
        check(True, 'level 10: 1C, it is in Noria at {},{}'.format(p.x, p.y))
        sim.run_until(lambda: c.sent['MapReady'] == 1, limit=motor.MAP_LOAD + 1, what='F3 12')
        check(c.sent['MoveGate'] == 1, 'F3 12 after the map change')
        fair(c)


def bot_career():
    print('the career on the real data: a knight hunts near Lorencia, an elf in Noria')
    with Sim(seed=3) as sim:
        events = traced(sim)
        dk = sim.bot('Knight', CharacterClass.DARK_KNIGHT)
        elf = sim.bot('Elfie', CharacterClass.ELF)
        sim.run_until(lambda: dk.counts['kills'] and elf.counts['kills'], limit=300, what='a kill each')
        for c, map_id, town in ((dk, 0, (142, 126)), (elf, 3, (174, 112))):
            g = c.brain.ground
            check(g.map_id == map_id and distance(*g.center, *town) <= 80,
                  '{} hunts {} at {},{} ({})'.format(c.bot.name, ', '.join(
                      sim.game.monster_info[t].name for t in c.brain.band), *g.center, sim.game.maps[map_id].name))
        picks = [e for e in events if e['event'] == 'ground']
        check(all(e['worth'] > 0 for e in picks), 'the trace has its picks: {}'.format(
            [(e['bot'], e['center'], e['worth']) for e in picks[:2]]))
        fair(dk, elf)


def bot_hunts(tmp):
    print('a bot hunts the spider, rests at low life and hunts on')
    with Sim(**world(tmp, SPIDER_ONLY, 'spider_only')) as sim:
        events = traced(sim)
        c = sim.bot('Botty')
        b = sim.enter('Bobby', at=(0, *free_tile(sim, 0, SPIDER_SPOT, 2, 3)))
        sim.run_until(lambda: c.counts['kills'], limit=120, what='a kill')
        check(c.brain.band == (3,), 'it walked to the spider and killed it')
        check(any(isinstance(p, SKill) and p.killer == c.cid for p in b.inbox), 'a player near sees the 17')
        p = c.player
        p.life = p.max_life // 5
        sim.run_until(lambda: isinstance(c.brain.activity, Rest), limit=2, what='resting')
        rested = sim.now
        sim.run_until(lambda: isinstance(c.brain.activity, Hunt), limit=600, what='hunting again')
        check(p.life >= p.max_life * c.bot.personality.rest_until,
              'at a fifth of its life it rests, {:.0f} game seconds, until {} of {}'.format(
                  sim.now - rested, p.life, p.max_life))
        kills = c.counts['kills']
        sim.run_until(lambda: c.counts['kills'] > kills, limit=60, what='another kill')
        check(True, 'then it hunts on')
        check([e['event'] for e in events if e.get('activity') == 'rest'][:2] == ['pick', 'done'],
              'the trace has the rest picked and done')
        fair(c)


def bot_dies(cfg):
    print('a bot dies to the hound, comes back and goes to its ground, not the hound\'s')
    with Sim(**cfg) as sim:
        events = traced(sim)
        hound = HOUND_SPOT
        c = sim.bot('Botty', at=(0, *free_tile(sim, 0, hound, 1, 1)))
        c.brain.next_think_at = sim.now + 10  # it looks away
        sim.run_until(lambda: c.counts['deaths'], limit=10, what='killed')
        sim.run_until(lambda: any(e['event'] == 'respawn' for e in events), limit=5, what='respawn')
        check(sim.game.maps[0].terrain.safe(c.player.x, c.player.y), 'killed, back in town')
        sim.run_until(lambda: isinstance(c.brain.activity, Hunt), limit=180, what='hunting again')
        g = c.brain.ground
        check(career.cell_of(*hound) not in {g.cell} and career.cell_of(*hound) in c.brain.deadly,
              'it hunts at {},{}, the hound\'s cell is a deadly one'.format(*g.center))
        fair(c)


def bot_unreachable(tmp):
    print('a bot gives up on a monster behind a wall')
    with Sim(**world(tmp, WALL_SPIDER, 'wall_spider')) as sim:
        events = traced(sim)
        spider = next(m for m in sim.game.monsters.values() if m.type_id == 3)
        monster.place(sim.game, spider, *WALL[1], spider.max_life, WALL[1], sim.now)
        c = sim.bot('Botty', at=(0, *WALL[0]))
        sim.run_until(lambda: any(e['event'] == 'left alone' for e in events), limit=60, what='left alone')
        tries = [e for e in events if e['event'] == 'unreachable']
        check(len(tries) == 3 and all(e['target'] == spider.cid for e in tries),
              'no way to it within {} steps three times, the spider 2 tiles away is left alone'.format(
                  motor.APPROACH_STEPS))
        fair(c)


def bot_points(cfg):
    print('a bot spends its points by its class build')
    with Sim(**cfg) as sim:
        c = sim.bot('Botty', at=(0, 140, 125))
        p = c.player
        before = p.strength, p.agility, p.vitality, p.energy
        command.level(sim.game, c, 2)
        sim.run_until(lambda: p.free_points == 0, limit=5, what='points spent')
        gained = tuple(a - b for a, b in zip((p.strength, p.agility, p.vitality, p.energy), before))
        check(gained == (3, 1, 1, 0) and c.sent['AddPoint'] == 5,
              'a knight at level 2: 5 F3 06, strength +3, agility +1, vitality +1: {}'.format(gained))
        fair(c)


def wizard_mana(tmp):
    print('a wizard casts energy ball while it has the mana, then swings')
    with Sim(**world(tmp, SPIDER_ONLY, 'spider_only')) as sim:
        c = sim.bot('Merlin', CharacterClass.DARK_WIZARD, at=(0, *free_tile(sim, 0, SPIDER_SPOT, 3, 4)))
        p = c.player
        sent = []
        send = c.send

        def spy(packet):
            sent.append((type(packet).__name__, p.mana))
            send(packet)
        c.send = spy
        p.mana = 3
        sim.run_until(lambda: any(name == 'Attack' for name, _ in sent), limit=60, what='a swing')
        casts = [mana for name, mana in sent if name == 'MagicAttack']
        swing = next(mana for name, mana in sent if name == 'Attack')
        check(casts and all(mana >= 1 for mana in casts) and swing < 1,
              'casts with {} mana, the swing with {}'.format(casts, swing))
        fair(c)


def bots_level():
    print('four classes level on the real data')
    with Sim(seed=4, exp_rate=10) as sim:
        bots = [sim.bot('Bot' + k, cls) for k, cls in sorted(CLASSES.items())]
        sim.run(600)
        levels = {c.bot.name: c.player.level for c in bots}
        check(all(level >= 3 for level in levels.values()), '10 game minutes at exp rate 10: {}'.format(levels))
        check(not any(c.counts['stuck'] for c in bots), 'none stuck')
        fair(*bots)


def bot_scenario(tmp):
    print('a bot\'s scenario: dumped, loaded, played on')
    path = os.path.join(tmp, 'bot.json')
    with Sim(seed=6) as sim:
        c = sim.bot('Botty')
        sim.run(300)
        sim.dump(c, path)
        p = c.player
        saved = p.level, p.exp, p.x, p.y, c.bot.seed, c.bot.personality
    sim, c = Sim.load(path)
    with sim:
        p = c.player
        check((p.level, p.exp, p.x, p.y, c.bot.seed, c.bot.personality) == saved,
              'the bot as it was: level {}, {} exp at {},{}, its seed and personality'.format(*saved[:4]))
        took = sim.run_until(lambda: p.exp > saved[1], limit=600, what='exp after the load')
        check(True, 'it plays on: {} exp {:.0f} game seconds later'.format(p.exp, took))
        fair(c)


def main():
    if sys.argv[1:2] == ['--digest']:
        logging.basicConfig(level=logging.ERROR)
        print(hunt_digest(int(sys.argv[2])))
        return 0
    logging.basicConfig(level=logging.ERROR, format='%(game_time)8.1f %(levelname)s %(name)s: %(message)s')
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='mu-sim-') as tmp:
        cfg = world(tmp)
        try:
            repeatable()
            walking(cfg)
            dying(cfg)
            monster_respawn(cfg)
            drops(cfg)
            regeneration(cfg)
            devil_square_round(cfg)
            scenario(tmp)
            bot_session(cfg)
            bot_motor(cfg)
            bot_career()
            bot_hunts(tmp)
            bot_dies(cfg)
            bot_unreachable(tmp)
            bot_points(cfg)
            wizard_mana(tmp)
            bots_level()
            bot_scenario(tmp)
        except AssertionError as e:
            print('FAILED:', e)
            return 1
    print('ALL OK in {:.1f} s'.format(time.perf_counter() - started))
    return 0


if __name__ == '__main__':
    sys.exit(main())
