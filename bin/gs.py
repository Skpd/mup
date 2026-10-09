import asyncio
import logging
import signal

from mup import config
from mup.bot.manager import BotManager
from mup.server import handlers
from mup.server.game import GameServer
from mup.server.protocol import BaseProtocol

logger = logging.getLogger('gs')


def create_gs(loop, cfg):
    gs = GameServer(loop, cfg)
    handlers.register(gs)
    if cfg.bots_enabled:
        BotManager(gs).login_all()
    return gs


def create_connection(cs):
    def f():
        proto = BaseProtocol(cs)
        return proto
    return f


async def main(loop, cfg):
    gs = create_gs(loop, cfg)
    gs.start()
    server = await loop.create_server(create_connection(gs), host='0.0.0.0', port=cfg.gs_port)
    logger.info('Game server on port %s, exp rate %s, database %s', cfg.gs_port, cfg.exp_rate, cfg.db_path)
    return gs, server

if __name__ == '__main__':
    cfg = config.load()
    config.setup_logging(cfg)
    main_loop = asyncio.get_event_loop()
    gs, t = main_loop.run_until_complete(main(main_loop, cfg))

    # ctrl-c and kill save the characters in game before exiting
    for sig in (signal.SIGINT, signal.SIGTERM):
        main_loop.add_signal_handler(sig, main_loop.stop)
    main_loop.run_forever()

    logger.info('Shutting down')
    t.close()
    gs.shutdown()
    main_loop.run_until_complete(t.wait_closed())
    main_loop.close()
