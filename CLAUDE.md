# mup: MU Online 0.97 server in Python

Hobby / learning project: a private server for the old MU Online 0.97 client (0.97b Chs, version `09704`).
Python 3.10 venv, asyncio, no framework. Work is planned in `docs/roadmap.md`, one milestone per session.

## Layout

- `bin/cs.py` connect server (port 44405), `bin/gs.py` game server (55901). Run from the repo root, `data/`
  (crypto keys, the client's terrains, `Gate.bmd`, `item.bmd` and `skill.bmd`, the server's `Monster.txt` /
  `MonsterSetBase.txt` / `Item.txt` / `Skill.txt` and `shop/`, mup's `ChaosMix.txt`), `config.ini` and the database
  are opened with relative paths.
  `bin/account.py`: accounts (create, password, personal code, ban, GM).
- `config.ini` (or the file in `MU_CONFIG`), read by `mup/config.py`: ports, advertised GS host, exp / drop rates,
  database file and autosave, monster, item, skill, shop and mix data files, fixed drops, account auto creation, log
  level, packet logging.
- `mup/packet/`: `base.py` has `Base(bytearray)` (type, size, head, sub) and the declarative `Packet`: `code`, `size`,
  `fields` as `(offset, name, type[, default])`, `entry` for lists. Field types carry the byte order (`u16` LE,
  `u16be`, `cid` BE). `Packet(name=value)` builds, `Packet(data)` parses into attributes; list packets have an
  `of(...)` builder from models. `client_packet/*` mapped by their `code` in `client.py`, `server_packet/*` aliased
  in `server.py` (`S...` names).
- `mup/server/`: `protocol.py` (framing, crypto, dispatch to handlers), `game.py` (`GameServer`: connections by cid,
  maps, the 100 ms game tick, entering, walking, relocating), `world.py` (maps, grids of who is where),
  `terrain.py`, `view.py` (what each client has in view, `12` / `13` / `14`, ground items `20` / `21`), `gate.py`,
  `monster.py` (monster data, spawns), `ai.py` (monster and summon behaviour), `path.py`, `combat.py` (hits, miss,
  ammunition, pace, death, respawn, regen), `stats.py` (what class, stats and items give, the client's formulas,
  `F3 06`), `experience.py` (kill exp, level up, death loss), `skill.py` (skill data, the list, learning, weapon
  skills), `casting.py` (skills on targets and areas, `1D` hits, buffs, teleport), `effect.py` (poison, ice, buffs,
  `1B`), `summon.py`, `item.py` (item data, wear slots, requirements, durability, wear), `inventory.py` (grids,
  what may be worn, moves between windows, potions, scrolls), `ground.py` (items on the ground, drop, pick up),
  `loot.py` (monster drops), `npc.py` (NPC windows, talking), `shop.py` (shops, the client's prices, buy, sell,
  repair), `warehouse.py`, `chaos.py` (chaos machine mixes), `jewel.py`, `command.py` (GM commands in chat),
  `chat.py` (chat, whispers), `party.py`, `trade.py`, `connect.py`,
  `handler/*` (one per packet, registered in `bin/gs.py` / `bin/cs.py`), `character.py` (creation rules, start
  and respawn gates). Game time is `GameServer.now`, the tick passes it on.
- `mup/model/` dataclasses. `mup/repository/`: SQLite storage (`database.py` schema migrations, account and
  character repositories). Characters in game live in memory and are saved by `GameServer.save`.
- `mup/common/crypt.py`: C3/C4 SimpleModulus, C1/C2 xor chain (`extract` / `pack`), login field xor.
- `docs/protocol-097.md`: the protocol as the client implements it. `docs/roadmap.md`: milestones.
- `tools/`: protocol extraction from the client with Ghidra. `tests/client.py`: scripted client test.

## Running

- Python: `./venv/bin/python` (`mu.pth` in its site-packages puts the repo on the path).
- `./run-gs.sh`: starts CS + GS, then a client. `./run-client.sh [client dir] [WxH] [desktop name]`: one client in a
  wine virtual desktop (native wine 9, `WINEPREFIX=~/projects/client`). Run it again for a second client.
- Client: `~/projects/client/mu/main.exe`, patched to connect to `mu.skpd.dev:44405` (resolves to 127.0.0.1) and
  serial `muonlineonpython`. `main.exe.orig` is the original. The other folders in `~/projects/client` are other
  versions with other protocols.
- Servers log at INFO. `log_packets = yes` in `config.ini` logs every packet in and out, tagged with the cid. For
  problems in the real client, ask the user to turn it on and paste the server log.

## Testing

- `./venv/bin/python tests/client.py`: starts its own CS and GS with a test config (ports 44415 / 55911, packet
  logging on, its own monster and drop files), plays two clients through login, character creation, walking, chat,
  combat, magic, drops, picking up, wearing and dropping items, a potion, disconnect, relog, GM commands, level up
  points, skills (scrolls, area hits, poison, teleport, weapon skills, an elf's buff, arrows, summons), monsters
  chasing and killing, respawn and a gate, NPCs (shops, wear and repair, the vault across a restart, a jewel, a
  mix, a trap), whispers, a party sharing a kill and trades, one function per area. Run it after every change and extend it with every feature. It checks raw
  offsets from the doc, never the packet definitions, so a wrong definition fails it.
- The real client is the final check: ask the user to try it and paste the log.

## Protocol rules

- **The client binary is the source of truth.** Check `docs/protocol-097.md` first. For anything not in it, read the
  client's handler or sender (`tools/extract.sh`, addresses in the doc) before implementing, and add what you
  confirm to the doc. Don't copy OpenMU layouts blindly: character info, server list and area skill hits differ
  for this client.
- Values are little endian, except object ids (cid): 2 bytes big endian, high bit is a flag.
- After login, client C1/C2 packets are xor chained from the byte after the header (`protocol.py`, `joined`).
  Connect server packets are plain.
- Some server packets are only accepted encrypted (C3/C4): list in the doc. Sent as C1 they are dropped and the
  client answers `C1 F1 03 00`.
- Character class: the create request sends class number << 2 (0, 16, 32, 48), everything else uses
  class number << 3 (`CharacterClass` values).
- Skills: the client sends the skill list index, server packets carry the skill number (`Player.skill()`).
- List packets: check the entry size in the doc (players in view are 32 bytes per entry).

## Reverse engineering

- `tools/extract.sh ~/projects/client/mu/main.exe /tmp/mu-extract`: about 2 minutes. Ghidra 12.1.4 in
  `/opt/ghidra_12.1.4_PUBLIC`, JDK 21 in `/usr/lib/jvm/java-21-openjdk-amd64` (the default java is 17, too old).
- Output: dispatch map, offsets read per handler, decompiled handlers and senders. Find a packet by the handler or
  sender address listed in the doc, then read the decompiled code.
- Mark everything added to the doc with how it was confirmed: code, traffic, or index only.

## Conventions

- Follow the existing style: one packet class per packet, one small handler per packet, game logic in `mup/server`
  modules rather than in handlers.
- Packet fields are copied from the doc table with their offsets; a layout mistake (overlap, past the size) fails
  at import. Logging: `logging.getLogger(__name__)`, no `print`.
- Schema changes: append a migration to `MIGRATIONS` in `mup/repository/database.py`, never edit a shipped one.
- Commit only when asked.
