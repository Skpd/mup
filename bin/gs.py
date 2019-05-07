import asyncio
from mup.server.game import GameServer
from mup.server.handler.attack import attack_handler
from mup.server.handler.char_list import char_list_handler
from mup.server.handler.chat import chat_handler
from mup.server.handler.close import close_handler
from mup.server.handler.create_character import create_character_handler
from mup.server.handler.delete_character import delete_character_handler
from mup.server.handler.exit import exit_handler
from mup.server.handler.game_start import game_start_handler
from mup.server.handler.login import login_handler
from mup.server.handler.magic import magic_attack_handler, aoe_magic_handler
from mup.server.handler.move import move_handler
from mup.server.handler.ping import ping_handler
from mup.server.protocol import BaseProtocol


def create_gs(loop):
    gs = GameServer(loop)
    gs.add_handler(0x18, None, print)  # todo rotate, send updates
    gs.add_handler(0x15, None, attack_handler)
    gs.add_handler(0x19, None, magic_attack_handler)
    gs.add_handler(0x1E, None, aoe_magic_handler)
    gs.add_handler(0x10, None, move_handler)
    gs.add_handler(0x00, None, chat_handler)
    gs.add_handler(0x0E, 0x00, ping_handler)
    gs.add_handler(0xF3, 0x00, char_list_handler)
    gs.add_handler(0xF3, 0x01, create_character_handler)
    gs.add_handler(0xF3, 0x02, delete_character_handler)
    gs.add_handler(0xF3, 0x03, game_start_handler)
    gs.add_handler(0xF3, 0x30, exit_handler)
    # cs.add_handler(0xF3, 0x06, add_point_handler)
    gs.add_handler(0xF1, 0x01, login_handler)
    gs.add_handler(0xF1, 0x03, close_handler)


    print('created GS', gs)
    return gs


def create_connection(cs):
    def f():
        print('incoming')
        proto = BaseProtocol(cs)
        return proto
    return f


async def main(loop):
    gs = create_gs(loop)
    server = await loop.create_server(create_connection(gs), host='0.0.0.0', port=55901)
    return server

if __name__ == '__main__':
    main_loop = asyncio.get_event_loop()
    t = main_loop.run_until_complete(main(main_loop))

    try:
        main_loop.run_forever()
    except KeyboardInterrupt:
        print()

    t.close()
    main_loop.close()
