# Roadmap

One milestone per session. Each starts from `CLAUDE.md` and the spec below, ends with `tests/client.py` extended and
passing, a manual test with the real client, and the status updated here.

Packet codes are hex, details in `docs/protocol-097.md`. Where a code's meaning is marked "usual", it is the common
0.97 meaning and still has to be confirmed by reading the client's handler.

| milestone | status |
|---|---|
| M0 protocol fixes, housekeeping | done |
| M1 persistence, character select flow | done |
| M2 world: maps, gates, monsters | done |
| M3 items | done |
| M4 combat and progression | todo |
| M5 NPCs, shops, warehouse, chaos machine | todo |
| M6 social: whisper, party, trade | todo |
| M7 guilds, quests, events, PK | todo |
| B0 bots: session, hunting, levelling (after M2) | todo |
| B1 bots: items, shops, map progression (after M3..M5) | todo |
| B2 bots: party, whisper, trade (after M6) | todo |
| B3 bots: guilds, quests, events (after M7) | todo |

## M0 protocol fixes, housekeeping

Fix what `docs/protocol-097.md` ("Differences with mup") found:

- `F3 03` character info: 42 byte client layout (money at 36, pk level 40, ctl 41), see the 2019 version.
- `15` damage: 13 bit value, colour flags in bits 5..7 of `[5]` (blue critical, green excellent, magenta).
- `12` players in view: 32 byte entries, effects at entry + 16 / + 17.
- `0E` ping: attack and magic speed are 2 bytes at 8 and 10. `F1 01` login tick is little endian.
- `F4 03` request: server code is 2 bytes. Weather `0F`: send a value the client understands or nothing.
- Drop the `F3 30` -> exit mapping. Fix the server list comment in `server_list.py`.

Housekeeping:
- Config file: ports, advertised GS host, exp / drop rates, log level. Default log level INFO with a packet
  DEBUG switch.
- Decide whether to move packets to declarative definitions (field list -> encode / decode) before the packet count
  grows. Most bugs so far were hand counted offsets and byte order.
  Decided: yes, all packets converted. `Packet` in `mup/packet/base.py`: fields as (offset, name, type) copied from
  the doc, types carry the byte order, layouts checked at import (order, overlaps, size). `tests/client.py` keeps
  checking raw offsets so it catches a wrong definition.

Done when: test checks money / pk level in character info and a damage above 255, real client shows the right zen.

## M1 persistence, character select flow

- SQLite with the stdlib `sqlite3`, a single file, no server. Starting point:
  ```
  accounts      (id, name UNIQUE, password_hash, ctl_code, active, created_at)
  characters    (id, account_id, slot, name UNIQUE, class, level, exp, level_up_points, str, agi, vit, ene,
                 life, mana, zen, map, x, y, dir, pk_level, pk_count, ctl_code, quest_state, created_at)
  items         (id, serial UNIQUE, owner 'inventory' | 'warehouse', character_id / account_id, slot,
                 item fields once M3 knows the format)
  skills        (character_id, slot, number)
  warehouses    (account_id, zen)
  guilds        (id, name UNIQUE, master_id, mark BLOB, score)
  guild_members (guild_id, character_id, status)
  ```
  Items get a unique serial (duplication checks later). Parties and trades stay in memory.
- Repositories replace `mup/mapper/`. Online state lives in memory, saved on logout, level up, item changes,
  every few minutes and on shutdown.
- Accounts: password hash, banned flag. Auto creating an account on first login stays as a config option.
- Characters: 5 slots, name rules, delete checks the personal code (`F3 02` `[14..23]`), class base stats from
  `~/projects/client/Data/Character/DefaultClassInfo.txt`, start map / position per class (Lorencia gate 17,
  elves Noria gate 27, from `Move/Gate.txt`).
- Logout `F1 02` (client sends the type: close, back to character select, back to server select; the result must be C3),
  remove the player from the world, then character list or disconnect.
- `F1 03` client reports: log reason (0 unencrypted packet, 6 decrypt failure).

Done when: create a character, go back to character select, restart the server, log in, the character is there
with its position and exp.

Done:
- `mup/repository/`: `database.py` (connect, schema as numbered migrations in `PRAGMA user_version`, WAL),
  `account.py`, `character.py`. All tables of the starting point exist; items, warehouses and guilds are empty
  until M3 / M5 / M7. Names are unique case insensitive.
- Accounts: scrypt password hash, `active` is the ban flag, `personal_code` column added (not in the starting
  point): auto created accounts get `personal_code` from the config. `bin/account.py` creates accounts, sets
  passwords and personal codes, bans.
- Characters: names of 3..10 letters / digits without `webzen` (the client hides those players), only first
  classes, 5 slots. Base stats from `DefaultClassInfo.txt` (`CLASS_INFO`), max life / mana are derived from it
  (`Player.max_life`), level up adds the class's points (MG 7). Start at a random spot of the gate area: the
  areas contain walls and a fountain, M2 has to pick a walkable tile.
- Saved on logout, disconnect, level up, every `autosave_interval` seconds and on SIGINT / SIGTERM. A second login
  of an account in game is refused with `F1 01` result 3.
- Logout `F1 02`: result handler read in the code, the request confirmed in traffic.
- Real client: created characters of three classes, character select, server select, exit, delete with a wrong
  and the right personal code, killed the exit monsters up to level 3, restarted the server twice: position,
  level, exp and level up points survived each restart.
- Found on the way: the client sends its key settings (`F3 30`) on every logout, mup doesn't store them yet.
- Placeholder monsters until M2: 3 budge dragons or spiders just outside each of the 4 Lorencia town exits
  (`LORENCIA_EXITS` in `game.py`), the client doesn't allow attacks in the safe zone. The test walks A and B to the
  east exit.

## M2 world: maps, gates, monsters

- Map registry for 0..10: Lorencia, Dungeon, Devias, Noria, Lost Tower, Exile, Arena, Atlans, Tarkan, Devil Square,
  Icarus. Terrain attributes (walls, safe zones) from `~/projects/client/Data/Terrain/TerrainN.att` (3 byte header,
  256 x 256 bytes, index `y * 256 + x`, `0x01` safe zone, `0x04` blocked, other bits not checked yet). Check them against the client's own `World*` files,
  some maps changed after 0.97.
- Walk validation against terrain. A spatial index for visibility (`map_view_wip.py` is a start).
- Gates and map change: `1C` both ways (server packet must be C3), gate data from the client's `Gate.bmd` or
  `Move/Gate.txt`.
- One game tick (100..250 ms) driving AI, respawn, regen, timers, autosave. Replaces the `Interval`s.
- Monsters: stats from `Monster/Monster.txt`, spawns from `Monster/MonsterSetBase.txt` (filter to maps 0..10), AI
  (idle, wander in spawn area, chase, attack, return), monster attacks on players (`15` to the player, life update
  `26`), player death (`17`) and respawn (`F3 04`) in the town, exp loss.
- Regen: life / mana (`26` / `27` usual meaning).

Done when: walk from Lorencia to Noria through a gate, monsters chase and hit, dying respawns in town.

Done:
- Client data in `data/`: the client's terrains (`World{n+1}/Terrain{n+1}.att`, 4 maps differ from the server's
  `Data/Terrain`), its `Gate.bmd`, the server's `Monster.txt` / `MonsterSetBase.txt` (`[world]` in `config.ini`).
  Terrain and gate formats, walkable bits (`0x04` wall, `0x08` no ground), the respawn, life, mana, map move and
  map loaded packets confirmed in the client's code, see the doc.
- `mup/server/world.py`: maps with an 8 x 8 cell grid each for players and monsters, `view.py` keeps what every
  client has in view (`c.view`) and sends `12` / `13` / `14` as players and monsters come and go, replacing the
  distance scans. `tools/map_view_wip.py` and the `move_strategy` modules are gone.
- Walks: the start must be walkable and within 15 tiles of the server's position, the walk stops before the first
  blocked step. New characters and respawns get a walkable tile of their gate area.
- Gates (`gate.py`): the request is accepted when the player's position or last walk is in the entrance area and
  the level is enough (MG two thirds), then `C3 1C` and everything in view again. The client's gate table has no
  gates to Lost Tower, Atlans, Tarkan and Icarus, their monsters wait for a warp command.
- One tick of 100 ms (`GameServer.run`) for monster AI (only monsters within 20 tiles of a player act), respawns,
  player respawn, regen and autosave. `mup/common/interval.py` is gone. 40 players among the real spawns: about 1 ms
  per tick.
- Monsters (`monster.py`, `ai.py`): the area and single spawns of maps 0..10 without Devil Square (event, M7), single
  spawns within 3 tiles of their spot (mup's choice). 2301 monsters, 87 of them on spots that are walls in this
  client's terrain (mostly Atlans) are left out, 2214 on the maps. AI: notice within view range, chase with an A* path
  (`path.py`) up to twice the view range and the spawn's range from home, attack (`18` animation `0x64`, `15` and
  `26` to the player) at attack speed, return home, wander within move range. Monsters don't enter the safe zone,
  don't stand on each other and don't attack players in it. Damage is the raw `Monster.txt` range, no defense or
  miss yet (M4).
- Death: `17` to the player and its viewers, `F3 04` after 3 s in the town of the map (Devias for Devias, Lost
  Tower, Icarus; Noria for Noria; Lorencia otherwise, usual rules), full life and mana. From level 10 a death costs
  2% of the level's exp (usual value; with mup's exp per level until M4's exp table). A character saved dead comes
  back in town.
- Regen every 3 s: 1% of max life, 3% of max mana (mup's own rates), `26` / `27` with `FF`.
- Test: own monster files (a spider that doesn't look, a dragon hitting for 1, a hound killing with one hit), a
  walk into a wall, chase and hit, regen, death and respawn, the gate to Noria at level 1 (refused) and level 10.
- Real client: looked fine.

## M3 items

- Reverse engineer the item format first: 4 bytes per item in `F3 10` (`[slot][4 bytes]`), 8 x 8 inventory grid,
  equipment slots. Inventory handler `0x414310`, item decode around `0x48d940`.
- Item definitions: client `Data/Local/item.bmd` (sizes, requirements, names; xor `FC CF AB` like `read_text.py`)
  plus `Item/Item.txt` for server side values.
- `F3 10` real inventory, `24` move / equip (result must be C3), equipment shown to others (`25` usual,
  appearance bytes in `12` and character list).
- Ground items: `20` in view, `21` gone, `22` pick up, `23` drop. Monster drops (`Item/ItemDrop.txt`) and zen.
- `26` use item: potions. Zen in character info.

Done when: kill a monster, pick up its drop, equip it, another client sees the new look, a potion heals.

Steps (each leaves something that runs and is tested):

0. Reverse engineering into the doc first (`tools/extract.sh`):
   - item bytes: `0x48d940` decodes an item (also called for `32`, `39`, `F3 14`): entry size, type / level / skill
     / luck / option / excellent / durability bits.
   - `F3 10` (`0x414310`, `[5]` count, entries from `[6]`): slot numbering, equipment slots, where the 8 x 8 grid
     starts.
   - server handlers `20` (`0x419f90`), `21` (inline), `22` (`0x41a0b0`), `23` (`0x41a3a0`), `24` (`0x41a680`),
     `25` (`0x416060`), `26` / `27` item counts, `28` (`0x48e0d0`). Do ground items share the 400 objects' cids?
   - client senders `22` (`0x4650a0`), `23` (`0x497760`), `24` (`0x422db0`, `0x474ac0`), the item use `26` sender
     (not in the sender index: inventory right click).
   - equipment look: the 10 bytes in `12` `[+5..14]` / `F3 00` `[+16..25]` (`0x4164b0`, `0x4124b0`), replacing the
     guesses in `appearance.py`.
   - requirements: the tooltip's formula (`0x487030`), so the server refuses what the client shows red. Potion
     stack limit if the client checks one.
   - `item.bmd`: 28676 bytes = 512 records of 56 bytes + 4, xor `FC CF AB`, 16 groups x 32 (type
     `group * 32 + index`, Horn of Uniria `0x1A2` = 13/2). Record field offsets.
1. Item data: `data/item.bmd` from the client, loader in `mup/server/item.py` (`ItemDef`). The server's `Item.txt`
   in `~/projects/client/Data/Item` is a later version (512 per group, DL), use it only for values the client
   doesn't have, where `index < 32` and the name matches. Potion heal values: small table, usual or mup's choice.
2. Model and storage: `ItemDef` (static) and `Item` (serial, type, level, durability, options) instead of
   `mup/model/item.py`'s mix. `Player.inventory` slot -> `Item` (equipment and grid). Migration rebuilding the empty
   `items` table with item columns, items saved with the character in one transaction, serials from a counter. One
   item codec (a `Packet` field type) for every packet carrying items.
3. Inventory rules, `mup/server/inventory.py`, no packets: grid occupancy by item size, free spot, equipment slot
   per item group, class flags, requirements (client formula), two-handed vs shield, bow / arrows, move validation.
4. Packets: real `F3 10` on join, `24` move / equip with the C3 result, `25` new look to viewers, real
   `appearance.equipment(p)` (fixes `12` and the character list).
5. Ground items: an item grid per map in `world.py`, `view.py` sends `20` / `21` as they come and go, expiry and
   owner priority (killer / dropper first for a few seconds, mup's choice) in the tick. `23` drop, `22` pick up
   (items and zen, zen into `Player.zen`).
6. Drops: on kill (`combat.hit_monster`) roll nothing / zen / item with `drop_rate`. Items from `item.bmd` by level
   near the monster's (usual 0.97 rule), potions by monster level, small option chances. `[world] item_drops` file
   for fixed drops per monster, the test config uses it. The later server's `ItemDrop.txt` is mostly post 0.97
   items, not used.
7. Potions: `26` use, heal, `26 FF` / `27 FF`, count down or delete, the potion delay the client's `FD` timer
   implies.
8. Test (raw offsets): empty `F3 10`, A kills a fixed drop monster, A and B see `20`, A picks up (`22`), both get
   `21`, A equips (C3 `24`), B gets `25`, refused moves (wrong slot, requirement, overlap), A drops and B picks up
   after the owner time, zen pickup, a potion heals, after relog `F3 10`, `F3 03` money and the look in the
   character list are kept. Then the real client.

Not in M3: durability loss (`2A`) and repair, jewels, shops and warehouse (M5), item stats in damage (M4), PK
item drop (M7).

Done:
- Doc: [Items](protocol-097.md#items) (item bytes, `item.bmd`, slots, slot classes, requirements, equipment look,
  item use lock) and the packets `F3 10`, `20`..`28`, `2A` both ways, all from code. 4 bytes per item, the client
  places a grid item by its top left slot. Zen on the ground has a 9 byte entry in `20`. `22` / `23` / `24` / `26`
  requests are C3.
- `data/item.bmd` (the client's) and `data/Item.txt` (the later server's: skill, options, drops) in
  `mup/server/item.py`, `ItemInfo` / `Item` / `GroundItem` in `mup/model/item.py`. `Player.inventory` is slot ->
  `Item`. Migration 2 rebuilds `items` with the item fields, items are saved with the character (`INSERT OR
  REPLACE` by serial, so an item that changed hands moves to its new owner), serials from the highest stored.
- `inventory.py`: grid fit, free slot (row by row), wear rules as the client checks them (slot class, rings both
  slots, one-handed weapons in the left hand for every class, class byte, magic gladiators as wizards or knights,
  no two-handed weapon sharing the hands but with arrows / bolts) plus the requirements the client doesn't check.
  Only the inventory window (0), trade / warehouse / chaos moves are refused. `25` to the viewers for slots 0..8.
- Ground items (`ground.py`): ids 0..999, an item grid per map in `world.py`, in `c.view` like players and monsters
  (`20` / `21`, `21` before a map change). 60 s on the ground, the killer alone may pick up for 10 s, player drops
  have no owner, pick up within 3 tiles, a drop farther than 3 tiles or on a wall lands on the player's tile. Zen
  goes into the money (`22 FE`, at most 2 000 000 000). All mup's choices.
- Drops (`loot.py`): an item when `rand(ItemRate) < 10 * drop_rate`, else zen when `rand(MoneyRate) < 10`
  (Monster.txt columns, the usual servers' shape with mup's numbers): 5..9% items, 35..46% zen on the real data.
  Items with the drop flag and a drop level up to 20 below the monster's, one item level per 10 monster levels
  up to `MaxItemLevel`, skill 15%, luck 10%, option 1 15% / 2 5%. Zen `level² / 2 + 5 level` +-25%. Fixed drops per
  monster type from `item_drops` (every line rolls on its own). Potions are as rare as any other item for now.
- Potions (`inventory.use`): healing `value * 10 - 2 * level` + 10 / 20 / 30 / 40% of max life, mana 20 / 30 / 40%
  (the later WebZen servers' formulas), then `2A` with the count or `28` for the last one, both unlock item use;
  other items only get the unlock (`26 FD`). No stacking on pick up yet.
- Test: drops seen by both players with the fall flag and the zen entry, the owner refusing A, pick up into slots
  12 / 13, zen, refused moves (overlap, a potion as helm, a wizard's strength), wearing the sword with `25` to the
  other player, a player drop picked up by the other, the look in the char list and in `12` after relog and
  restart, the inventory and money after relog and restart, a potion healing with `28` after it.
- Real client: looked fine.

## M4 combat and progression

- Damage formulas per class, stats and weapon, defense, miss, critical / excellent rolls, attack range and speed checks.
- Exp per monster level, experience table, stat points (`F3 06`), derived life / mana per class.
- Skills: data from `skill.bmd` / `Skill/Skill.txt` (mana, range, damage), learned from scrolls / orbs (`26`),
  area hits from the client's `1D` report instead of the server side guess, elf buffs, summons (`1F`), `1B` cancel,
  `F3 11` add / remove.

## M5 NPCs, shops, warehouse, chaos machine

- NPC spawns, talk `30` (result must be C3), shops `31`..`34` from `Shop/*.txt`, repair.
- Warehouse `81`..`83`. Chaos machine `86` / `87`, basic mixes.

## M6 social: whisper, party, trade

- Whisper `02` / `0C` (usual), confirm the client chat layout `00` (not reviewed yet).
- Party `40`..`44`: invite, list, member life, exp share.
- Trade `36`..`3D`.
- GM commands through chat.

## M7 guilds, quests, events, PK

- Guilds `50`..`56`, `5A`..`5D`, guild war `60`..`64`, 32 byte guild mark.
- Second class quests `A0`..`A3` (client `quest.bmd`).
- Devil Square `90`..`96`, `99`.
- PK: levels, timers, item drop on death.

## Bots

AI players: ordinary accounts and characters that start at level 1, play through the same rules as clients and grow
by a career plan. Each B milestone follows the M milestones it needs.

Design:
- In process, no socket: a `BotSession` is a connection the game can't tell from a client. `view.py` shows every
  non monster connection as a player, so real clients see bots with no extra packets.
- Input: the bot builds client packets (`CMove`, `CAttack`, `CJoinGame`, ...) and dispatches them through
  `server.handlers` like `protocol.py` does. Bots can do nothing a client can't, every server check applies to them.
- Output: `write()` hands the built server packets to the brain. `Packet` keeps its values as attributes, so they are
  typed events (`SDamage`, `SKill`, `SLevelUp`, later trade and party requests) without parsing.
- Perception: `c.view`, what a client standing there has been shown.
- Brain in three layers:
  - career: hunting grounds derived from data, not hand written. `Monster.txt` levels and `MonsterSetBase.txt`
    spawns grouped by map and area; pick the one near the bot's level. Map progression from the `Gate.bmd` graph
    (entrance -> target, minimum level, MG 2/3). Stat build per class as point ratios. Personality: risk, greed,
    chattiness, play schedule (log in and out in sessions, progress only while online).
  - activity: small state machines (travel, hunt, loot, rest, restock / sell, trade, idle in town) with timeouts,
    picked by priority every few seconds: survive > restock > sell / repair > upgrade > level.
  - motor: `path.find_path` for short paths, cached gate to gate waypoints for long ones, attack speed cadence,
    skill choice by mana and range.
- Driven by the M2 game tick, each bot thinks every 0.5..1 s, staggered. No timers of its own.
- Storage: a migration with `bots (character_id, personality, career state as JSON, rng seed, schedule)`. Bot
  characters are ordinary `characters` rows saved by `GameServer.save`. `bin/account.py` creates bots.
- Bots get items and zen only from the drops, shops and kills players get, nothing out of thin air.
- Players can tell a bot when they ask or trade with it.

## B0 bots: session, hunting, levelling

- `Session` base for `BaseProtocol` and `BotSession` (cid, acc, player, view, playing, write). Move logic the
  handlers reach through the connection (`send_all`, which skips non `BaseProtocol` connections) into `mup/server`.
- Bot accounts and characters: the `bots` table, creation in `bin/account.py`, login without a password (set
  `acc`, dispatch `CJoinGame`), cids from the player range.
- Walk pacing: `move_handler` sets the position to the walk target at once, a bot sends short segments and waits
  for each like M2 monsters do (`next_step_at`). Measure the real client's walk speed per tile from logged traffic.
- Hunting grounds from `Monster.txt` / `MonsterSetBase.txt`, hunt / rest / return to town, death and respawn.
- Stat points through `F3 06` (handler still to write, see M4) by the class build.
- A simulation script: game and bots without sockets on a fast clock (`GameServer.now`), reports levels over
  simulated hours. Used to balance exp rates and bot behaviour.

Done when: the test's client sees a bot appear, walk, attack and kill; the simulation takes bots of all four
classes a few levels up without getting stuck; the real client watches a bot hunt outside Lorencia.

## B1 bots: items, shops, map progression

- Loot (`22`), potions (`26`), equip upgrades by class and stat requirements, gear requirements feed the stat build.
- Town trips: sell, buy potions, repair (M5 shops).
- Skills (M4), map progression through gates as levels unlock the next hunting ground.

Done when: a bot left alone goes from Lorencia to the next map's hunting ground with better gear than it started
with.

## B2 bots: party, whisper, trade

- Party: accept invites from players near the bot's level, follow the leader, share exp.
- Whisper and chat: canned lines per situation, a tiny command grammar (`price X`, `buy X`, `sell X`), wts / wtb
  ads in town chat. A language model for chat lines only, optional: async, with a timeout, never in the tick, no
  decisions.
- Item value: base price from `Item/ItemValue.txt` / `Shop/*.txt`, use to the bot (upgrade for its class and
  stats, jewels it needs), market memory: a `trades` log table, median price per item, level and options.
- Bot to bot: a server side order book matches wants and offers, bots meet in town and trade through the real
  `36`..`3D` flow so players see it.
- Bot to player: trade requests arrive as events, the bot checks every change of the window against its reserve
  price, accepts only after the other side has been unchanged for ~2 s, never takes unknown items, daily spend cap
  per bot.

Done when: a player buys an item from a bot and sells one to it in the real client; two bots trade with each other
in Lorencia.

## B3 bots: guilds, quests, events

- Join and create guilds, second class quest when the career reaches it, Devil Square entry.

## Reverse engineering backlog

- Unknown server packets: `01`, `0B`, `0C`, `1A`, `71`, `F1 04` / `05` / `12`, `F3 07` / `08` / `13` / `14` /
  `20` / `22` / `23` / `30` / `40`.
- Client packets missed by the sender index (whisper and others), and `97`, `98`, `A2`, `C1`.
- Client chat layout `00`.
