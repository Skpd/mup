import asyncio
from mup.server.connect import ConnectServer
from mup.server.handler.server_info import server_info_handler
from mup.server.handler.server_list import server_list_handler
from mup.server.protocol import BaseProtocol


def create_cs():
    cs = ConnectServer()
    cs.add_handler(0xF4, 0x02, server_list_handler)
    cs.add_handler(0xF4, 0x03, server_info_handler)

    print('created CS', cs)
    return cs


def create_connection(cs):
    def f():
        print('incoming')
        proto = BaseProtocol(cs)
        return proto
    return f


async def main(loop):
    cs = create_cs()
    server = await loop.create_server(create_connection(cs), host='0.0.0.0', port=44405)
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
