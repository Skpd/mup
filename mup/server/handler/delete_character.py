from mup.error import NotFoundError
from mup.packet.client_packet.char_delete import CharDelete
from mup.packet.server import SCharDeleted
from mup.server.protocol import BaseProtocol


def delete_character_handler(msg: CharDelete, proto: BaseProtocol):
    print('char delete request {} {}'.format(msg.name, msg.passw))
    # todo verify personal code (msg.passw)

    if proto.acc is None:
        return

    players = proto.server.player_mapper
    try:
        p = players.load(msg.name)
    except NotFoundError:
        p = None

    ok = p is not None and p.account.id == proto.acc.id
    if ok:
        players.delete(p)

    proto.write(SCharDeleted(success=ok))
