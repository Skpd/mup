from mup.error import NotFoundError
from mup.packet.client import CJoinGame
from mup.packet.server import SStats, SInventory, SMeetPlayer, SMeetMonster, SSkillList
from mup.server.protocol import BaseProtocol


def game_start_handler(msg: CJoinGame, proto: BaseProtocol):
    print('Game join request for {}'.format(msg.name))

    try:
        player = proto.server.player_mapper.load(msg.name)
    except NotFoundError:
        player = None

    if player is None or proto.acc is None or player.account.id != proto.acc.id:
        print('{} is not a character of this account'.format(msg.name))
        return

    proto.player = player
    proto.playing = True

    """
hp              c1:07:26:fe:00:8f:00
mana            c1:08:27:fe:01:fa:00:5b:
weather         c1:04:0f:29:
check exe?      c1:06:03:29:1d:50:
stats           c3:4f:f5:30:01:00:93:36:00:4e:2d:15:20:fb:eb:0e:ae:8a:3b:f3:85:42:d4:e1:9f:74:3c:c5:58:39:c2:53:f0:be:8b:8b:0c:22:1d:80:6b:75:90:6d:1a:2f:61:f8:2a:f7:dc:d3:55:d7:59:43:76:9d:e4:24:ba:0a:76:46:f2:40:8f:ba:13:02:0b:ff:1d:73:e4:2b:c5:6b:55:
inventory       c4:00:66:dd:ab:0b:4e:82:40:d6:52:49:d4:e1:3b:8a:1b:54:4c:5e:70:d8:1a:7d:48:d6:11:13:74:d9:bb:a3:49:a1:8b:be:cf:f6:1f:7c:0b:50:b1:b0:41:97:a2:16:f2:31:af:9b:7c:94:f1:b2:d5:e0:78:d9:27:46:8c:72:74:aa:25:45:70:9e:a3:3a:f4:9f:83:15:5a:a1:c5:f0:f7:14:19:f2:87:b6:11:90:02:04:31:0a:af:7d:af:9b:9a:47:30:ce:7c:44:
magic           c1:11:f3:11:04:00:11:01:01:0b:03:02:04:04:03:05:05:
announcement    c1:1e:0d:00:57:65:6c:63:6f:6d:65:20:74:6f:20:4d:75:4f:6e:6c:69:6e:65:20:64:75:6d:6d:79:00:
meet self       c2:00:25:12:01:92:c8:84:46:00:ff:ff:33:33:3c:0d:b6:c0:00:00:00:00:00:64:75:6d:6d:79:00:00:00:00:00:84:46:02:00:
qwe binds       c1:13:f3:30:00:05:0b:04:11:00:00:00:00:00:09:00:04:08:0f
"""
    proto.write(bytearray([0xC1, 0x04, 0x0F, 0x29]))  # weather

    proto.write(SStats(player))
    proto.write(SInventory(player.inventory))
    proto.write(SMeetPlayer(proto.cid, player))
    proto.write(SSkillList(player.skills))

    for c in proto.server.get_monsters_within(player.map_id, player.x, player.y):
        proto.write(SMeetMonster(c))

    for c in proto.server.get_players_within(player.map_id, player.x, player.y):
        if c != proto:
            proto.write(SMeetPlayer(c.cid, c.player))
            c.write(SMeetPlayer(proto.cid, player))
