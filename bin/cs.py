import asyncio
import logging

from mup import config
from mup.server.connect import ConnectServer
from mup.server.handler.server_info import server_info_handler
from mup.server.handler.server_list import server_list_handler
from mup.server.protocol import BaseProtocol

logger = logging.getLogger('cs')


def create_cs(cfg):
    cs = ConnectServer(cfg)
    cs.add_handler(0xF4, 0x02, server_list_handler)
    cs.add_handler(0xF4, 0x03, server_info_handler)
    return cs


def create_connection(cs):
    def f():
        proto = BaseProtocol(cs)
        return proto
    return f


async def main(loop, cfg):
    cs = create_cs(cfg)
    server = await loop.create_server(create_connection(cs), host='0.0.0.0', port=cfg.cs_port)
    logger.info('Connect server on port %s, game server %s:%s', cfg.cs_port, cfg.gs_host, cfg.gs_port)
    return server

if __name__ == '__main__':
    cfg = config.load()
    config.setup_logging(cfg)
    main_loop = asyncio.new_event_loop()
    t = main_loop.run_until_complete(main(main_loop, cfg))

    try:
        main_loop.run_forever()
    except KeyboardInterrupt:
        print()

    t.close()
    main_loop.close()
