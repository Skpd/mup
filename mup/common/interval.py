import asyncio


class Interval:
    def __init__(self, callback, interval):
        self.interval = interval
        self.callback = callback

        self.__running = False
        self.__task = None

    def start(self):
        if not self.__running:
            self.__running = True
            self.__task = asyncio.ensure_future(self.__run())

    def stop(self):
        if self.__running:
            self.__running = False
            self.__task.cancel()

    async def __run(self):
        while self.__running:
            await asyncio.sleep(self.interval)
            self.callback()
