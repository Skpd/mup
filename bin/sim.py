"""
The game on a fast clock (mup.sim) with bots (mup.bot): how far they get in game hours, what they spend their time
on, whether they get stuck or break the client's rules, how fast the game runs. A bot's situation can be dumped to a
scenario file and played on from it, a run is replayed by its seed.

usage: ./venv/bin/python bin/sim.py [--bots dk,dw,elf,mg] [--hours H] [--seed S] [--exp-rate R] [--drop-rate R]
                                    [--trace FILE]
                                    [--packets BOT] [--digest] [--profile]
       ./venv/bin/python bin/sim.py --until T --dump BOT FILE   (T: game seconds or h:mm[:ss])
       ./venv/bin/python bin/sim.py --load FILE [--hours H]
       ./venv/bin/python bin/sim.py --grounds CLASS              the hunting grounds the career picks by level
The real data of config.ini's [world] (or MU_CONFIG's), an in-memory database. docs/bots.md, S0 and B0.
"""
import argparse
import cProfile
import json
import logging
import pstats
import sys
import time
from collections import Counter

from mup import config
from mup.bot import CLASSES, career
from mup.config import PACKET_LOGGER
from mup.model.item import GRID
from mup.server import character
from mup.sim import Sim, Hunter

logger = logging.getLogger('sim')

WORLD = ('monster_info', 'monster_spawns', 'item_info', 'item_drops', 'skill_info', 'shops', 'mixes')
LEVELS = (1, 2, 3, 5, 7, 10, 15, 20, 30, 40, 50, 70, 100)  # --grounds


def game_time(text):
    """Seconds from 'h:mm[:ss]' or seconds."""
    parts = [float(p) for p in text.split(':')]
    if len(parts) == 1:
        return parts[0]
    while len(parts) < 3:
        parts.append(0.0)
    hours, minutes, seconds = parts
    return hours * 3600 + minutes * 60 + seconds


def clock(seconds):
    return '{}:{:02}:{:02}'.format(int(seconds // 3600), int(seconds % 3600 // 60), int(seconds % 60))


def class_name(class_type):
    return next(k for k, v in CLASSES.items() if v == class_type.base)


def report(sim, bots, wall, started_at, levels_at_start, final=False):
    played = sim.now - started_at
    print('game time {}, {:.1f} s: {:.0f} times real time, {} flow fields made'.format(
        clock(sim.now), wall, played / wall if wall else 0, sim.bots.flows.made))
    for c in bots:
        p, n = c.player, c.counts
        if p is None:
            print('  {:<10} logged out'.format(c.bot.name))
            continue
        gained = p.level - levels_at_start[c.bot.name]
        print('  {:<10} {:<3} level {:>3} ({:+.1f}/h) {:<8} kills {:>5} deaths {:>3} stuck {:>2} errors {:>2} '
              'refused {:>3}  {}'.format(c.bot.name, class_name(p.class_type), p.level,
                                          gained / (played / 3600) if played else 0, sim.game.maps[p.map_id].name[:8],
                                          n['kills'], n['deaths'], n['stuck'], n['errors'], n['refused'],
                                          activities(n)))
        print('  {:<10} items {} zen {} potions {} learned {} worn {} owned {}: {}'.format(
            '', n['items'], n['zen'], n['potions'], n['learned'], n['worn'], n['owned'], worn(p)))
        print('  {:<10} trips {} sold {} for {} zen, bought {} for {}, repairs {} for {}, stored {}; {} zen'.format(
            '', n['trips'], n['sold'], n['sold zen'], n['bought'], n['spent'], n['repairs'], n['repair zen'],
            n['stored'], p.zen))
        if c.brain is not None and len(c.brain.visited) > 1:
            visits = sorted(c.brain.visited.items(), key=lambda v: v[1])
            print('  {:<10} maps: {}'.format('', ', '.join('{} {}'.format(sim.game.maps[m].name, clock(t))
                                                         for m, t in visits)))
        if final:
            for message in c.checker.errors[:5]:
                print('      error:', message)
    if final:
        by_class = {}
        for c in bots:
            if c.player is not None:
                by_class.setdefault(class_name(c.player.class_type), []).append(c.player.level)
        print('  levels by class:', ', '.join('{} {:.1f}'.format(k, sum(v) / len(v)) for k, v in by_class.items()))


def worn(p):
    """What p's player wears, +levels and the skill bit."""
    return ', '.join('{}{}{}'.format(i.info.name, ' +{}'.format(i.level) if i.level else '', ' (s)' if i.skill else '')
                     for slot, i in sorted(p.inventory.items()) if slot < GRID) or 'nothing'


def activities(counts):
    """Share of the time per activity."""
    times = {k[5:]: v for k, v in counts.items() if k.startswith('time ')}
    total = sum(times.values()) or 1
    return ' '.join('{} {:.0%}'.format(k, v / total) for k, v in sorted(times.items(), key=lambda kv: -kv[1]))


def run(sim, bots, seconds, hourly, levels):
    """Runs seconds of game time, a report every game hour when hourly."""
    started, at = time.perf_counter(), sim.now
    end = sim.now + seconds
    while sim.now < end:
        sim.run(min(3600.0, end - sim.now))
        if hourly and sim.now < end:
            report(sim, bots, time.perf_counter() - started, at, levels)
    return time.perf_counter() - started, at


class OneBot(logging.Filter):
    """Lets through the packet log of one bot only, like log_packets for it."""

    def __init__(self, sim, name):
        super().__init__()
        self.sim, self.name = sim, name.lower()

    def filter(self, record):
        if record.name != PACKET_LOGGER:
            return True
        c = next((c for c in self.sim.bots.sessions.values() if c.bot.name.lower() == self.name), None)
        return c is not None and bool(record.args) and record.args[0] == c.cid


def grounds(cfg_overrides, name):
    """The grounds the career picks on the class's start map by level (no items, no travel), and the best of each
    map the gates reach."""
    class_type = CLASSES[name]
    with Sim(0, **cfg_overrides) as sim:
        game = sim.game
        start = game.gates[character.start_gate(class_type)].map_id
        maps = sim.bots.grounds
        for level in LEVELS:
            p = career.built(class_type, level)
            reach = career.reachable_maps(game.gates, start, level, class_type == CLASSES['mg'])
            fights = career.fights_for(game, p, {t for m in reach for g in maps.get(m, {}).values() for t in g.counts})
            ranked = career.rank(game, p, maps[start], fights=fights)
            deadly = career.deadly_cells(maps[start], fights)
            print('level {:>3}: {} deadly cells, gates reach maps {}'.format(level, len(deadly), sorted(reach)))
            for value, g, band in ranked[:3]:
                print('    {:>6.2f} exp/s at {},{}: {}'.format(value, *g.center, ', '.join(
                    game.monster_info[t].name for t in band)))
            for m in sorted(reach - {start}):
                best = career.rank(game, p, maps.get(m, {}), fights=fights)[:1]
                for value, g, band in best:
                    print('    {:>6.2f} exp/s at {},{} of {}: {}'.format(value, *g.center, game.maps[m].name, ', '.join(
                        game.monster_info[t].name for t in band)))


def main(argv):
    parser = argparse.ArgumentParser(description='The game on a fast clock with bots')
    parser.add_argument('--bots', default='dk,dw,elf,mg', help='classes of the bots, comma separated: ' +
                        ', '.join(sorted(CLASSES)))
    parser.add_argument('--hours', type=float, default=1.0, help='game hours to run')
    parser.add_argument('--until', type=game_time, help='run until this game time instead')
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--exp-rate', type=float)
    parser.add_argument('--drop-rate', type=float)
    parser.add_argument('--trace', metavar='FILE', help='the bots\' events as JSON lines')
    parser.add_argument('--packets', metavar='BOT', help='the packets of one bot in the log, like log_packets')
    parser.add_argument('--dump', nargs=2, metavar=('BOT', 'FILE'), help='at the end, the bot to a scenario file')
    parser.add_argument('--load', metavar='FILE', help='play a scenario on, no other bots')
    parser.add_argument('--grounds', metavar='CLASS', choices=sorted(CLASSES), help='print the grounds by level')
    parser.add_argument('--digest', action='store_true', help='print the digest of everything sent to the bots')
    parser.add_argument('--profile', action='store_true', help='print the functions that took the most time')
    parser.add_argument('--log', default='WARNING', help='log level')
    args = parser.parse_args(argv)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(game_time)9.1f %(levelname)s %(name)s: %(message)s'))
    logging.basicConfig(level=args.log.upper(), handlers=[handler], force=True)

    cfg = config.load()
    overrides = {k: getattr(cfg, k) for k in WORLD}
    if args.exp_rate is not None:
        overrides['exp_rate'] = args.exp_rate
    if args.drop_rate is not None:
        overrides['drop_rate'] = args.drop_rate
    if args.grounds:
        logging.getLogger().setLevel(logging.ERROR)
        grounds(overrides, args.grounds)
        return 0

    if args.load:
        sim, c = Sim.load(args.load, Hunter, **overrides)
        bots = [c] if c in sim.bots.sessions.values() else []
    else:
        sim = Sim(args.seed, **overrides)
        names = Counter()
        bots = []
        for name in args.bots.split(','):
            if name not in CLASSES:
                parser.error('no class {}, one of {}'.format(name, ', '.join(sorted(CLASSES))))
            names[name] += 1
            bots.append(sim.bot('Bot{}{}'.format(name.capitalize(), names[name]), CLASSES[name]))
    trace = open(args.trace, 'w') if args.trace else None
    if trace:
        sim.bots.trace = lambda record: trace.write(json.dumps(record) + '\n')
    if args.packets:
        logging.getLogger(PACKET_LOGGER).setLevel(logging.DEBUG)
        logging.getLogger(PACKET_LOGGER).addFilter(OneBot(sim, args.packets))
    with sim:
        levels = {c.bot.name: c.player.level for c in bots}
        seconds = args.until - sim.now if args.until is not None else args.hours * 3600
        profile = cProfile.Profile() if args.profile else None
        if profile:
            profile.enable()
        wall, at = run(sim, bots, seconds, not args.profile, levels)
        if profile:
            profile.disable()
        report(sim, bots, wall, at, levels, final=True)
        if args.digest:
            print('digest', sim.digest())
        if args.dump:
            name, path = args.dump
            c = next((c for c in bots if c.bot.name.lower() == name.lower()), None)
            if c is None:
                print('no bot', name)
                return 1
            sim.dump(c, path)
            print('dumped {} at {} to {}'.format(c.bot.name, clock(sim.now), path))
        if profile:
            pstats.Stats(profile, stream=sys.stdout).sort_stats('tottime').print_stats(20)
    if trace:
        trace.close()
    errors = sum(c.counts['errors'] for c in bots)
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
