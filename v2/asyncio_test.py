import asyncio
import inspect
from asyncio.windows_events import ProactorEventLoop
if __name__ == "__main__":
    policy=asyncio.get_event_loop_policy()
    loop=policy.get_event_loop()
    print(inspect.getmodule(loop).__file__)
    asyncio.wait_for
    pass