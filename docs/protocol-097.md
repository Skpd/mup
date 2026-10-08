# MU 0.97 protocol, as the client implements it

Extracted from the client binary itself, not from emulator sources or OpenMU.

| | |
|---|---|
| binary | `~/projects/client/mu/main.exe` (0.97b Chs, "0.97.2.0"), md5 `13068908ce2aaa018627a02c06c6d733` |
| original | `main.exe.orig`, md5 `2ecc66720cac2a461dcf8325f87dd74f`, differs only in server address and serial |
| version | `09704`, stored in the exe as `1;:49` (each byte + position + 1) |
| tools | Ghidra 12.1.4 headless, `tools/ghidra/*.java`, `tools/extract_*.py`, driven by `tools/extract.sh` |

Every layout below is marked with where it was confirmed:

- **code**: read in the decompiled handler / sender
- **traffic**: seen byte for byte in a real client session (`1791384296.log`)
- **index**: only located by the scripts, layout not reviewed

Offsets are from the start of the packet, including the header. Multi-byte values are little endian unless
marked BE. Object ids (`cid`) are always 2 bytes BE, the high bit is a flag the client masks off (`& 0x7FFF`).

## Regenerating

```
tools/extract.sh ~/projects/client/mu/main.exe /tmp/mu-extract
```

About 2 minutes. Writes `receive.txt` (dispatch map), `receive_fields.txt` (offsets each handler reads),
`send.txt` (client packets, heuristic) and the decompiled `dispatcher.c`, `handlers.c`, `senders.c`.
The two address arguments of `extract.sh` (receive switch jump `0x4213f4`, receive loop `0x420c93`) are specific
to this exe.

## Where things are in main.exe

| what | address |
|---|---|
| receive loop + dispatcher (`ProtocolCompiler` / `TranslateProtocol` inlined) | `0x420c70` |
| head code switch | `0x4213ee`: `cmp esi, 0xF4`, index table `0x422a50`, jump table `0x4228e4` |
| packet builder `AddData(this, data, size, xor)` | `0x403390` |
| xor range helper (inlined single byte appends) | `0x403290` |
| C3/C4 encrypt | `0x4e7220` (called twice: size, then encrypt) |
| C3/C4 decrypt | `0x4e7290` |
| `send` thunk / import | `0x4e7188` / IAT `0x4f7338` (ws2_32 ordinal 19) |
| default server address pointer, port | `0x503bf8` -> slot `0x4fc35e` (`mu.skpd.dev`, patched, 3 of the 4 address slots), `0x503bfc` = 44405 |

## Transport

Headers: `C1 size head ...` and `C3 size ...`, `C2 sizeH sizeL head ...` and `C4 sizeH sizeL ...` (code).

**Client -> server, C1/C2.** The header (type, size, head) is plain, everything after it, sub code included,
is xor chained with the 32 byte key `E7 6D 3A 89 ...` (`buf[i] ^= buf[i-1] ^ key[i % 32]`). Exception: the
connect server requests (`F4 02`, `F4 03`) are plain (code, traffic).

**C3/C4.** Built as C1/C2 (fields xor chained as above), then the first byte after the header is replaced by
a serial counter and the rest is SimpleModulus encrypted (code).

- The client keeps one serial counter for packets it sends (`0x57c7113`) and one it expects (`0x57c7114`),
  shared by C3 and C4, incremented per packet, 1 byte.
- **When a received C3/C4 serial doesn't match**, the client resyncs its counter but treats that packet as
  *not encrypted* (code, dispatcher `0x420d4a..`).

**Packets the client only accepts encrypted.** The dispatcher passes an "arrived encrypted" flag to these
handlers. On a C1 or a serial mismatch they drop the packet and the client sends `C1 F1 03 00` (code):

`16` exp, `19` skill animation, `1C` teleport, `1E` area skill animation, `24` item move result, `29`,
`30` npc talk, `F1 02` logout result (types 1 and 2), `F3 03` character info, `F3 10` inventory.

**Login fields** (account, password) are additionally xored with `FC CF AB` (repeating) before the chain
(code, traffic).

## Connect server

| dir | packet | layout | src |
|---|---|---|---|
| S>C | `C1 04 00 01` hello | head `00` is shared with chat: while the client is on the server list screen (state 2) any `00` makes it request the server list | code `0x414960` |
| C>S | `C1 04 F4 02` server list request | no fields, not xored, sent on hello (and again when the list is refreshed) | code, traffic |
| S>C | `C2 F4 02` server list | `[5]` count, then **4 bytes per server**: `[+0..1]` server code (`group * 20 + index`), `[+2]` load %, `[+3]` unused. Group 12 has a special name | code `0x411e60` |
| C>S | `C1 06 F4 03` server info request | `[4..5]` server code (little endian) | code `0x4caad0`, traffic |
| S>C | `C1 16 F4 03` server info | `[4..18]` ip string (15 bytes + 0), `[20..21]` port | code `0x421a28` |
| S>C | `C1 F4 05` | no fields, sets the client's scene state to 1, meaning not reviewed | code |

## Game server, server -> client

| packet | layout | src |
|---|---|---|
| `C1 F1 00` join result | `[4]` 1 = ok, `[5..6]` player cid BE, `[7..11]` version, must equal the exe's decoded version (`09704`), otherwise "version not matched" | code `0x4122b0` |
| `C1 F1 01` login result | `[4]` result: 1 ok; 0, 2..6, 8..0x0D, 0x11, 0xC0..0xC2 and 0xD0..0xD2 each show their own message, anything else a generic error. Usual meanings: 0 wrong password, 3 in use, 4 server full, 5 banned, 6 new version | code (dispatcher) |
| `C3 F1 02` logout result | `[4]` type. 0: the client destroys its window (exits), the encryption isn't checked. 1: must be encrypted, back to character select, the client resets its game state and sends `F3 00` itself. 2: must be encrypted, the client closes the connection and goes back to the server list (scene 2). Other values: ignored | code `0x4129f0` |
| `C1 F3 00` character list | `[4]` count, then 26 bytes per character: `[+0]` slot, `[+1..10]` name, `[+11]` 0, `[+12..13]` level, `[+14]` ctl code (`& 0x10` marks the char), `[+15]` class, `[+16..25]` equipment | code `0x4124b0` |
| `C1 F3 01` character created | `[4]` result: 1 ok, 0 opens dialog `0x36`, 2 dialog `0x37` (texts not looked up, mup uses the usual meanings: 0 bad or taken name, 2 no free slot). `[5..14]` name, `[15]` slot: index into the 5 character slots (`0x364` bytes each at `DAT_07a5f9b8`). Class and look come from the create screen, nothing after `[15]` is read | code `0x412600` |
| `C1 F3 02` character deleted | `[4]` 1 opens dialog `0x39` (deleted), anything else dialog `0x3a` showing the value as an error code. mup: 0 no such character of the account, 2 wrong personal code | code (dispatcher) |
| `C3 F3 03` character info | **42 bytes**, must be encrypted: `[4]` x `[5]` y `[6]` map `[7]` direction, `[8..11]` exp, `[12..15]` next exp, then 2 bytes each: `[16]` level up points `[18]` str `[20]` agi `[22]` vit `[24]` ene `[26]` life `[28]` max life `[30]` mana `[32]` max mana, `[34..35]` unused, `[36..39]` money, `[40]` pk level, `[41]` ctl code | code `0x413380` |
| `C1 F3 05` level up | `[4]` level `[6]` level up points `[8]` max life `[10]` max mana, 2 bytes each | code `0x41b6d0` (asm) |
| `C4 F3 10` inventory | must be encrypted | code `0x414310` (index) |
| `C1 F3 11` skill list | `[4]` count (max 20), then 3 bytes each: `[+0]` slot, `[+1]` skill number, `[+2]` unused. `[4]` = `0xFE`: set one skill, `[5]` slot `[6]` number. `[4]` = `0xFF`: remove skill at slot `[5]` | code `0x414010` |
| `C1 00` chat | `[3..12]` name, `[13..72]` message. Message prefix `~` party, `@` guild, `#` shout, anything else normal chat | code `0x414960` |
| `C1 0D` notice | `[3]` type, `[4..]` text | code `0x414d10` (reads only) |
| `C1 0F` weather | `[3]` high nibble: 0 turns the effect off, 1 turns it on with intensity low nibble * 6, other values are ignored | code (dispatcher) |
| `C1 10` walk | `[3..4]` cid, `[5]` x `[6]` y, `[7]` direction in the high nibble | code `0x414ea0` |
| `C2 12` players in view | `[4]` count, then **32 bytes** each: `[+0..1]` cid, `[+2]` x `[+3]` y, `[+4]` class `<< 5 \| 2nd class << 4 \| pose` (pose 2..4 pick a sitting / leaning animation), `[+5..14]` equipment, `[+16]` effects bits 0..3 (poison, ice, damage buff, defense buff) and `[+17]` bit 0 another effect, `[+18..27]` name, `[+28]` target x `[+29]` target y, `[+30]` direction << 4 \| pk level, `[+31]` unused. Names containing `webzen` are skipped | code `0x4164b0` |
| `C2 13` monsters in view | `[4]` count, then 12 bytes each: `[+0..1]` cid, `[+2]` type, `[+3]` unused, `[+4..5]` effects (little endian word: bits 0..3 as in players in view, bit 8 the `[+17]` effect), `[+6]` x `[+7]` y, `[+8]` target x `[+9]` target y, `[+10]` direction in the high nibble | code `0x416fe0` |
| `C1 14` out of view | `[3]` count, then cids from `[4]` | code (dispatcher, asm) |
| `C1 15` damage | `[3..4]` target cid, `[5..6]` BE: damage in the low 13 bits (max 8191), flags in bits 13..15 of the BE word, i.e. `[5]` bits 5..7: bit 7 blue (critical), bit 6 green (excellent), bit 5 magenta, green wins over blue over magenta, none: orange, red when the target is you. Damage 0 shows a miss. When the target is you the client also subtracts the damage from a 2 byte field of its character (`+0x1C`, likely life) | code `0x4179a0` |
| `C3 16` kill exp | must be encrypted: `[3..4]` killed cid, `[5..6]` exp BE, `[7..8]` damage BE, shown like a damage number | code `0x4199a0` |
| `C1 17` killed | `[3..4]` cid of the dying object, nothing else is read | code (dispatcher, asm) |
| `C1 18` animation | `[3..4]` cid, `[5]` direction, `[6]` animation | code `0x417fc0` |
| `C3 19` skill animation | must be encrypted: `[3]` skill number, `[4..5]` caster cid, `[6..7]` target cid (bit 15: effect applied) | code `0x4186b0` |
| `C3 1E` area skill animation | must be encrypted: `[3]` skill number, `[4..5]` caster cid, `[6]` x `[7]` y | code `0x418fd0` |

Everything else the client handles is listed in appendix A with the offsets its handler reads.

## Game server, client -> server

| packet | layout | src |
|---|---|---|
| `C3 F1 01` login | 49 bytes: `[4..13]` account, `[14..23]` password (both xor `FC CF AB`), `[24..27]` tick count (GetTickCount, little endian), `[28..32]` version `09704`, `[33..48]` serial | code `0x4cb840`, traffic |
| `C1 F1 03` client report | `[3]` 3, `[4]` reason: 0 = a must-be-encrypted packet arrived unencrypted. When a C3/C4 packet fails to decrypt the client sends reason 6 instead, itself encrypted (C3) with a random byte appended | code (handlers, dispatcher) |
| `C1 F3 00` character list request | no fields | traffic |
| `C1 F3 01` create character | `[4..13]` name, `[14]` class: **class number << 2** (0 dw, 16 dk, 32 elf, 48 mg), everything the server sends uses class number << 3 | traffic |
| `C3 F1 02` logout request | 5 bytes, sent encrypted: `[4]` type as in the result: 0 close the game, 1 character select, 2 server select. Preceded by `F3 30` (types 0 and 1 before, type 2 right after). The sender isn't in the sender index, a byte scan for `F1` head stores doesn't find it either | traffic (`1791402942.log`, `1791403016.log`) |
| `C1 F3 30` key settings | 18 bytes, sent on every logout: `[4..13]` 10 bytes (skill hotkeys, all 0 when none set), `[14..17]` `09 00 04 08` seen. Layout not reviewed, presumably what the server sends back with `F3 30` on join | traffic |
| `C3 31` | no fields, sent right after `F3 00` when going back to character select. Usual meaning: close the NPC / shop window | traffic |
| `C1 F3 02` delete character | `[4..13]` name of the selected character, `[14..23]` the personal code as typed in the dialog (10 byte buffer, zero padded) | code `0x4c3f40` |
| `C1 F3 03` enter game | `[4..13]` name | traffic |
| `C1 F3 06` add level up point | 5 bytes, `[4]` stat (`03` seen) | index `0x49c950`, traffic |
| `C3 0E 00` ping | 12 bytes: `[4..7]` tick count, `[8..9]` attack speed, `[10..11]` magic speed | code `0x40e2a0`, traffic |
| `C1 10` walk | `[3]` x `[4]` y (start of the walk), `[5]` direction << 4 \| step count, `[6..]` step directions, one per nibble, high nibble first. Sent with 0 steps to only turn | traffic |
| `C1 15` attack | `[3..4]` target cid, `[5]` attack animation (0x64 seen), `[6]` direction | traffic, code `0x4650a0` |
| `C1 18` animation | `[3]` direction, `[4]` animation (0x66 seen when turning) | traffic |
| `C3 19` skill on target | `[3]` skill list index, `[4..5]` target cid | code `0x462140` |
| `C3 1E` area skill | `[3]` skill list index, `[4]` x `[5]` y, `[6]` direction | code `0x46f270` |
| `C3 1D` area skill hits | `[3]` skill list index, `[4]` x `[5]` y, `[6]` serial, `[7]` count, then target cids. **Has a byte between y and count** that OpenMU's 0.75 layout doesn't | code `0x442610` |
| `C1 00` chat | name + message, not reviewed yet: send a chat line and check the log | - |

## Differences with mup

The layout differences found in the first review were fixed in roadmap M0 (character info, damage, players in view,
ping, login tick, weather, server list / info, `F3 30`). Still open:

1. **`C3 1D` area skill hits are not handled**. The client reports what an area skill hit, mup instead
   damages everything within 5 tiles of the target point when the skill is cast (`handler/magic.py`) and logs
   the reports as unhandled. Roadmap M4.
2. **C3 serial**: mup's counter (`Crypt.encrypt_sequence`) starts at 0 per connection, matching the client after
   a fresh start. If the client keeps its counter across a reconnect, the first encrypted packet of the new
   connection (character info) would be treated as unencrypted and dropped. Not seen yet, worth knowing when
   adding "switch server".

## Appendix A: server -> client dispatch map

Output of `ReceiveDispatch.java` (head / sub code, case address, functions called) merged with the offsets the
handler reads (`extract_handlers.py`, reads through pointer aliases and list entries are not followed).
`F1` / `F3` / `F4` sub codes are read from `[3]` for C1 and `[4]` for C2 (C3/C4 arrive decrypted as C1/C2).

```
00 @ 00421ace calls [FUN_00414960@00414960]
    414960 reads 3:4, 7:4, 11:2, 13:1, 14:ptr
01 @ 00421adc calls [FUN_0043dc30@0043dc30, FUN_0045f640@0045f640]
02 @ 00421b1f calls [FUN_0045e470@0045e470, FUN_004043d0@004043d0, FUN_0045e860@0045e860]
03 @ 00421bb3 calls [FUN_0040e1d0@0040e1d0, FUN_00403390@00403390, FUN_00408f70@00408f70, FUN_004234a0@004234a0]
0B @ 00421c4a calls [FUN_004b3370@004b3370]
0C @ 00421cf3 calls [FUN_0045e860@0045e860]
0D @ 00421d17 calls [FUN_00414d10@00414d10]
    414d10 reads 3:1, 4:ptr
0F @ 0042215b calls []
10 @ 00421d25 calls [FUN_00414ea0@00414ea0]
    414ea0 reads 3:1, 4:1, 5:1, 6:1, 7:1
11 @ 00421d34 calls [FUN_00415250@00415250]
    415250 reads 3:1, 4:1, 5:1, 6:1
12 @ 00421d42 calls [FUN_004164b0@004164b0]
    4164b0 reads 1:1, 23:ptr
13 @ 00421dd3 calls [FUN_00416fe0@00416fe0]
    416fe0 reads 4:1, 7:ptr
14 @ 00421dfd calls [FUN_0043db80@0043db80]
15 @ 00421f56 calls [FUN_004179a0@004179a0]
    4179a0 reads 1:ptr, 3:1, 4:1, 5:1, 6:1
16 @ 00421fb0 calls [FUN_004199a0@004199a0]
    4199a0 reads 3:1, 4:1, 5:1, 6:1, 7:1, 8:1
17 @ 00421fbf calls [FUN_0043dc30@0043dc30]
18 @ 00421f64 calls [FUN_00417fc0@00417fc0]
    417fc0 reads 3:1, 4:1, 5:1, 6:1
19 @ 00421f73 calls [FUN_004186b0@004186b0]
    4186b0 reads 3:1, 4:1, 5:1, 6:1, 7:1
1A @ 00421f83 calls [FUN_00419570@00419570]
    419570 reads 3:1, 4:1
1B @ 00421fa2 calls [FUN_00418500@00418500]
    418500 reads 3:1, 4:1, 5:1
1C @ 00422191 calls [FUN_00415520@00415520]
    415520 reads 3:1, 4:1, 5:1, 6:1, 7:1
1E @ 00421f92 calls [FUN_00418fd0@00418fd0]
    418fd0 reads 3:1, 4:1, 5:1, 6:1, 7:1
1F @ 00421de1 calls [FUN_004172c0@004172c0]
    4172c0 reads 4:1, 11:ptr
20 @ 00421e3c calls [FUN_00419f90@00419f90]
    419f90 reads 4:1, 5:ptr, 9:ptr
21 @ 00421e4a calls []
22 @ 00421e90 calls [FUN_0041a0b0@0041a0b0]
    41a0b0 reads 1:ptr, 3:1, 4:ptr
23 @ 00421e9e calls [FUN_0041a3a0@0041a3a0]
    41a3a0 reads 3:1, 4:1
24 @ 00421eac calls [FUN_0041a680@0041a680]
    41a680 reads 3:1, 4:1, 5:ptr
25 @ 00421f48 calls [FUN_00416060@00416060]
    416060 reads 3:1, 4:1, 5:ptr, 6:1, 8:1
26 @ 00422130 calls [FUN_0041bcd0@0041bcd0]
27 @ 0042213e calls [FUN_0041bfc0@0041bfc0]
28 @ 00421ffb calls [FUN_0048e0d0@0048e0d0]
29 @ 0042214c calls [FUN_0041c6f0@0041c6f0]
    41c6f0 reads 3:1, 4:2
2A @ 00422504 calls [FUN_0041c3b0@0041c3b0]
    41c3b0 reads 3:1, 4:1, 5:1
30 @ 00422031 calls [FUN_0041abc0@0041abc0]
    41abc0 reads 3:1
31 @ 00422040 calls [FUN_00414890@00414890]
    414890 reads 4:1, 5:1, 6:ptr
32 @ 0042204e calls [FUN_0048d940@0048d940, FUN_004043d0@004043d0]
    48d940 reads 1:ptr
33 @ 0042208c calls [FUN_004239b0@004239b0, FUN_00403940@00403940, FUN_004043d0@004043d0, FUN_0048e650@0048e650]
34 @ 004220de calls [FUN_004239b0@004239b0, FUN_0045c9f0@0045c9f0, FUN_00403940@00403940, FUN_004043d0@004043d0]
    45c9f0 reads 70:2, 88:2, 90:2, 1386:2, 1388:2, 1390:2, 1394:2, 1396:2, 1400:2, 1402:2, 1408:2, 1410:2, 1412:2, 1414:2, 1416:2, 1418:1, 1419:1
36 @ 0042233c calls [FUN_0040e1d0@0040e1d0, FUN_00403390@00403390, FUN_004234a0@004234a0, FUN_0048e650@0048e650]
37 @ 00422413 calls [FUN_0041d1b0@0041d1b0]
    41d1b0 reads 3:1
38 @ 00422421 calls [FUN_0048e0d0@0048e0d0, FUN_004043d0@004043d0]
39 @ 00422446 calls [FUN_0048d940@0048d940, FUN_004043d0@004043d0]
    48d940 reads 1:ptr
3A @ 00422472 calls []
3B @ 0042248b calls []
3C @ 00422498 calls [FUN_004043d0@004043d0]
3D @ 004224f6 calls [FUN_0041d6f0@0041d6f0]
    41d6f0 reads 3:ptr
40 @ 00422231 calls []
41 @ 00422255 calls []
  sub switch on packet[3], 00..05
  41 00 @ 00422266 calls [FUN_0045e860@0045e860]
  41 01 @ 00422274 calls [FUN_0045e860@0045e860]
  41 02 @ 00422282 calls [FUN_0045e860@0045e860]
  41 03 @ 00422290 calls [FUN_0045e860@0045e860]
  41 04 @ 0042229e calls [FUN_0045e860@0045e860]
  41 05 @ 004222ac calls [FUN_0045e860@0045e860]
42 @ 004222cf calls [FUN_0041de50@0041de50]
    41de50 reads 4:1, 16:ptr
43 @ 004222dd calls [FUN_0045e860@0045e860]
44 @ 00422300 calls []
45 @ 00421def calls [FUN_00416a40@00416a40]
    416a40 reads 4:1, 7:ptr
50 @ 0042259b calls []
51 @ 004225bf calls [FUN_0041df50@0041df50]
    41df50 reads 3:1
52 @ 004225cd calls []
53 @ 0042263f calls [FUN_0041e110@0041e110]
    41e110 reads 3:1
54 @ 0042264d calls [FUN_004035b0@004035b0, FUN_004037c0@004037c0]
55 @ 004226db calls [FUN_0045d160@0045d160]
56 @ 00422728 calls [FUN_0041ea70@0041ea70]
    41ea70 reads 3:1
5A @ 00422736 calls [FUN_0041e8b0@0041e8b0]
    41e8b0 reads 4:1, 7:ptr
5B @ 00422744 calls [FUN_0041e900@0041e900]
    41e900 reads 4:1, 8:ptr
5C @ 00422752 calls [FUN_0041e750@0041e750]
    41e750 reads 3:1, 4:1, 5:ptr, 13:ptr
5D @ 00422760 calls [FUN_0041e860@0041e860]
    41e860 reads 3:1, 4:1
60 @ 0042276e calls [FUN_0041eb80@0041eb80]
    41eb80 reads 3:1
61 @ 0042277c calls [FUN_0041eb30@0041eb30]
    41eb30 reads 3:4, 7:4, 11:1
62 @ 0042278a calls [FUN_0041ec90@0041ec90]
    41ec90 reads 3:4, 7:4, 11:1, 12:1
63 @ 00422798 calls [FUN_0041f0e0@0041f0e0]
    41f0e0 reads 3:1
64 @ 004227a6 calls []
71 @ 004227c7 calls [FUN_0041d800@0041d800]
81 @ 004227d5 calls [FUN_0041d970@0041d970]
    41d970 reads 3:1
82 @ 004227e3 calls [FUN_0041dbe0@0041dbe0]
83 @ 004227f1 calls [FUN_0041dc30@0041dc30]
    41dc30 reads 3:1
86 @ 004227ff calls [FUN_0041f960@0041f960]
    41f960 reads 3:1, 4:ptr
87 @ 0042280d calls [FUN_0041fa20@0041fa20]
90 @ 0042281b calls [FUN_0041fa70@0041fa70]
    41fa70 reads 3:1
91 @ 00422829 calls [FUN_0041fec0@0041fec0]
    41fec0 reads 3:1
92 @ 00422837 calls [FUN_0045d100@0045d100]
93 @ 0042284b calls [FUN_0041ff30@0041ff30]
    41ff30 reads 3:1, 4:1, 5:ptr
94 @ 00422859 calls [FUN_00420240@00420240]
    420240 reads 4:2, 6:4, 8:2, 10:2
95 @ 00422867 calls [FUN_004202a0@004202a0]
    4202a0 reads 4:2
96 @ 00422875 calls [FUN_004202c0@004202c0]
    4202c0 reads 4:4, 6:2, 8:2
99 @ 00422883 calls [FUN_004202f0@004202f0]
    4202f0 reads 3:1
A0 @ 00422891 calls [FUN_00420320@00420320]
    420320 reads 3:1
A1 @ 0042289f calls [FUN_00420350@00420350]
    420350 reads 3:1, 4:1
A2 @ 004228ad calls [FUN_00420380@00420380]
    420380 reads 3:1, 4:1, 5:1
A3 @ 004228bb calls [FUN_004203c0@004203c0]
    4203c0 reads 1:ptr, 3:1, 4:1, 5:1, 6:1
F1 @ 004213fb calls []
  sub switch on packet[3], 00..12
  F1 00 @ 00421418 calls [FUN_004122b0@004122b0]
      4122b0 reads 4:1, 5:1, 6:1, 7:1
  F1 01 @ 00421426 calls []
    sub switch on packet[4], 00..D2
    F1 01 00 @ 00421445 calls []
    F1 01 01 @ 0042145e calls [FUN_00408c40@00408c40]
    F1 01 02 @ 00421486 calls []
    F1 01 03 @ 0042149f calls []
    F1 01 04 @ 004214b8 calls []
    F1 01 05 @ 004214d1 calls []
    F1 01 06 @ 004214ea calls []
    F1 01 08 @ 00421503 calls []
    F1 01 09 @ 0042151c calls []
    F1 01 0A @ 00421535 calls []
    F1 01 0B @ 0042154e calls []
    F1 01 0C @ 00421567 calls []
    F1 01 0D @ 00421580 calls []
    F1 01 11 @ 00421599 calls []
    F1 01 C0 @ 004215b2 calls []
    F1 01 C1 @ 004215cb calls []
    F1 01 C2 @ 004215e4 calls []
    F1 01 D0 @ 004215b2 calls []
    F1 01 D1 @ 004215cb calls []
    F1 01 D2 @ 004215e4 calls []
  F1 02 @ 00421616 calls [FUN_004129f0@004129f0]
      4129f0 reads 4:1
  F1 03 @ 00421666 calls []
  F1 04 @ 004216da calls []
    sub switch on packet[4], 00..03
    F1 04 00 @ 0042172e calls []
    F1 04 01 @ 004216ef calls [FUN_00411c90@00411c90]
    F1 04 02 @ 0042173d calls []
    F1 04 03 @ 0042174c calls []
  F1 05 @ 0042175b calls []
    sub switch on packet[4], 00..03
    F1 05 00 @ 0042177f calls []
    F1 05 01 @ 00421770 calls []
    F1 05 02 @ 0042178e calls []
    F1 05 03 @ 0042179d calls []
  F1 12 @ 00421625 calls []
F3 @ 004217ac calls []
  sub switch on packet[4], 00..40
  F3 00 @ 004217d6 calls [FUN_004124b0@004124b0]
      4124b0 reads 4:1, 20:ptr
  F3 01 @ 004217e4 calls [FUN_00412600@00412600]
      412600 reads 4:1, 5:4, 9:4, 13:2, 15:1
  F3 02 @ 004217f2 calls []
  F3 03 @ 00421821 calls [FUN_00413380@00413380]
      413380 reads 4:1, 5:1, 6:1, 7:1, 8:4, 12:4, 16:2, 18:2, 20:2, 22:2, 24:2, 26:2, 28:2, 30:2, 32:2, 36:4, 40:1, 41:1
  F3 04 @ 00421830 calls [FUN_00413b00@00413b00]
  F3 05 @ 0042184d calls [FUN_0041b6d0@0041b6d0]
  F3 06 @ 0042185b calls [FUN_0041b9a0@0041b9a0]
      41b9a0 reads 1:ptr, 4:1
  F3 07 @ 00421869 calls [FUN_004239b0@004239b0, FUN_00403940@00403940]
  F3 08 @ 004218c4 calls [FUN_0041c2b0@0041c2b0]
      41c2b0 reads 4:1, 5:1, 6:1
  F3 10 @ 0042183e calls [FUN_00414310@00414310]
      414310 reads 5:1, 6:ptr
  F3 11 @ 004218d2 calls [FUN_00414010@00414010]
      414010 reads 4:1, 5:1, 6:1
  F3 13 @ 004218e0 calls [FUN_0043dc30@0043dc30, FUN_0043f6f0@0043f6f0]
  F3 14 @ 0042190a calls [FUN_0048d940@0048d940, FUN_004043d0@004043d0]
      48d940 reads 1:ptr
  F3 20 @ 00421941 calls []
  F3 22 @ 00421951 calls []
  F3 23 @ 00421962 calls []
  F3 30 @ 004219d4 calls [FUN_0041ff50@0041ff50]
  F3 40 @ 004219e2 calls [FUN_0041f7e0@0041f7e0]
      41f7e0 reads 4:1, 5:1, 6:1
F4 @ 004219f0 calls [FUN_00423fe0@00423fe0, FUN_00411960@00411960, FUN_004e7c6c@004e7c6c, FUN_0045e860@0045e860, FUN_00411e60@00411e60]
    411e60 reads 1:ptr, 2:ptr, 5:ptr, 6:ptr
```

## Appendix B: client -> server senders

Head codes and the functions building them (`extract_senders.py`). The heuristic misreads some packets because
the client inlines its packet builder in several ways, so treat this as a list of where to look, not as layouts.

```
00  0041f0e0, 004d2b21
03  00420890
0E  0040e2a0
10  004650a0
11  00462140
15  004650a0
18  0041ec90, 0041f0e0, 004650a0, 0046c770, 0046c9c0, 00474ac0
19  00462140
1C  00474030
1D  00442610
1E  0046f270
22  004650a0
23  00497760
24  00422db0, 00474ac0
30  004650a0
31  00401920, 0041fa70, 0049d500, 0049e7b0
33  00497760
34  004a19f0
36  0046a340
3C  00497760, 004a1070
3D  004a1070
40  0046a340
43  0049c5b0
50  0046a340
71  0041d800
81  004232c0
82  004aa5c0
86  00497760
87  004aa3a0
90  0049d500
97  0049dff0
98  0049dff0
A0  004650a0
A2  00401d00, 00402660
C1  004916f0
F1  00408f70, 004129f0, 00413380, 00414310, 00415520, 00418fd0, 004199a0, 0041a680, 0041abc0, 0041c6f0, 004cb840
F3  004129f0, 00415520, 0049c950, 004c0000, 004c3f40, 004d0b30
F4  00414960, 004caad0, 004cb840
```
