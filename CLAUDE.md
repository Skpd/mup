# mup: MU Online 0.97 server in Python

Hobby / learning project: a private server for the old MU Online 0.97 client (0.97b Chs, version `09704`).
Python 3.10 venv, asyncio, no framework. Work is planned in `docs/roadmap.md`, one milestone per session.

## Layout

- `bin/cs.py` connect server (port 44405), `bin/gs.py` game server (55901). Run from the repo root, the crypto
  keys in `data/` and `config.ini` are opened with relative paths.
- `config.ini` (or the file in `MU_CONFIG`), read by `mup/config.py`: ports, advertised GS host, exp / drop rates,
  log level, packet logging.
- `mup/packet/`: `base.py` has `Base(bytearray)` (type, size, head, sub) and the declarative `Packet`: `code`, `size`,
  `fields` as `(offset, name, type[, default])`, `entry` for lists. Field types carry the byte order (`u16` LE,
  `u16be`, `cid` BE). `Packet(name=value)` builds, `Packet(data)` parses into attributes; list packets have an
  `of(...)` builder from models. `client_packet/*` mapped by their `code` in `client.py`, `server_packet/*` aliased
  in `server.py` (`S...` names).
- `mup/server/`: `protocol.py` (framing, crypto, dispatch to handlers), `game.py` (`GameServer`: connections by cid,
  distance based visibility, monster respawn), `connect.py`, `combat.py`, `handler/*` (one per packet, registered
  in `bin/gs.py` / `bin/cs.py`).
- `mup/model/` dataclasses, `mup/mapper/memory.py` in-memory storage (the Mongo mappers next to it are old and unused).
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
  logging on), plays two clients through login, character creation, walking, chat, combat, magic, disconnect and
  relog. Run it after every change and extend it with every feature. It checks raw offsets from the doc, never the
  packet definitions, so a wrong definition fails it.
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
- Storage is in memory until roadmap M1 (SQLite).
- Commit only when asked.
