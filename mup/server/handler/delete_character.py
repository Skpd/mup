from mup.packet.client_packet.char_delete import CharDelete
from mup.packet.server import SCharDeleted
from mup.server.protocol import BaseProtocol


def delete_character_handler(msg: CharDelete, proto: BaseProtocol):
    print('char delete request {} {}'.format(msg.name, msg.passw))
    # todo delete
    # todo verify
    proto.write(SCharDeleted(success=True))
