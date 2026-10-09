from mup.packet.client import (CGuildRequest, CGuildAnswer, CGuildListRequest, CGuildLeave, CGuildMasterAnswer,
                               CGuildCreate, CGuildCancel)
from mup.server import guild
from mup.server.protocol import BaseProtocol


def guild_request_handler(msg: CGuildRequest, proto: BaseProtocol):
    if proto.player is None:
        return
    guild.request(proto.server, proto, msg.cid & 0x7FFF)


def guild_answer_handler(msg: CGuildAnswer, proto: BaseProtocol):
    if proto.player is None:
        return
    guild.answer(proto.server, proto, msg.answer == 1, msg.cid & 0x7FFF)


def guild_list_handler(msg: CGuildListRequest, proto: BaseProtocol):
    if proto.player is None:
        return
    guild.send_list(proto.server, proto)


def guild_leave_handler(msg: CGuildLeave, proto: BaseProtocol):
    if proto.player is None:
        return
    guild.leave(proto.server, proto, msg.name, msg.personal_code)


def guild_master_answer_handler(msg: CGuildMasterAnswer, proto: BaseProtocol):
    if proto.player is None:
        return
    guild.master_answer(proto.server, proto, msg.answer == 1)


def guild_create_handler(msg: CGuildCreate, proto: BaseProtocol):
    if proto.player is None:
        return
    guild.create(proto.server, proto, msg.name, msg.mark)


def guild_cancel_handler(msg: CGuildCancel, proto: BaseProtocol):
    if proto.player is None:
        return
    guild.cancel(proto.server, proto)
