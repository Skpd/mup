from mup.packet.client import CKeySettings
from mup.server.protocol import BaseProtocol


def key_settings_handler(msg: CKeySettings, proto: BaseProtocol):
    """The client sends them on logout: before it to the character select, after it to the server list. Saved with
    the character, sent back on join."""
    if proto.player is not None:
        proto.player.key_settings = msg.data
    elif proto.left is not None:
        proto.left.key_settings = msg.data
        proto.server.characters.save_key_settings(proto.left)
