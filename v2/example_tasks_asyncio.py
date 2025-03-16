import math
import sys
import time
import warnings
import asyncio
from functools import partial

import httpx
import httpcore._async.http11

# Default is 4096
httpcore._async.http11.AsyncHTTP11Connection.READ_NUM_BYTES = 100_000


class AsyncioDisplay:
    """Helper class to handle display and cancellation with asyncio."""
    def __init__(self):
        self.title = ""
        self.value = 0
        self.max = 0
        self.task = None

    def set_title(self, title):
        self.title = title
        
    def set_value(self, value):
        self.value = value
        
    def set_max(self, max):
        self.max = max
        
    def set_cancel(self, cancel_func):
        self.cancel_func = cancel_func


async def get(display):
    try:
        url = sys.argv[1]
    except IndexError:
        url = "http://google.com/"
    try:
        size_guess = int(sys.argv[2])
    except IndexError:
        size_guess = 5269
    fps = 60
    display.set_title(f"Fetching {url}...")
    
    task = asyncio.current_task()
    display.set_cancel(task.cancel)
    
    try:
        start = time.monotonic()
        downloaded = 0
        last_screen_update = time.monotonic()
        async with httpx.AsyncClient() as client:
            for i in range(10):
                print("Connection attempt", i)
                try:
                    async with client.stream("GET", url) as response:
                        total = int(response.headers.get("content-length", size_guess))
                        display.set_max(total)
                        async for chunk in response.aiter_raw():
                            downloaded += len(chunk)
                            if time.monotonic() - last_screen_update > 1 / fps:
                                display.set_value(downloaded)
                                last_screen_update = time.monotonic()
                    break
                except httpcore._exceptions.ReadTimeout:
                    pass
            else:
                print("response timed out 10 times")
                return
        end = time.monotonic()
        dur = end - start
        bytes_per_sec = downloaded / dur
        print(f"Downloaded {downloaded} bytes in {dur:.2f} seconds")
        print(f"{bytes_per_sec:.2f} bytes/sec")
    except asyncio.CancelledError:
        print("Download was cancelled")
        raise
    return 1


async def count(display, period=.1, max=60):
    display.set_title(f"Counting every {period} seconds...")
    display.set_max(60)
    
    task = asyncio.current_task()
    display.set_cancel(task.cancel)
    
    try:
        for i in range(max):
            await asyncio.sleep(period)
            display.set_value(i)
    except asyncio.CancelledError:
        print("Counting was cancelled")
        raise
    return 1


async def check_latency(display=None, period=0.1, duration=math.inf):
    task = None
    if display is not None:
        task = asyncio.current_task()
        display.set_cancel(task.cancel)
    elif duration == math.inf:
        warnings.warn("check_latency may not terminate until the process is killed")
    
    try:
        start_time = asyncio.get_event_loop().time()
        while True:
            if duration != math.inf and asyncio.get_event_loop().time() - start_time >= duration:
                break
                
            target = asyncio.get_event_loop().time() + period
            await asyncio.sleep(period)
            print(asyncio.get_event_loop().time() - target, flush=True)
    except asyncio.CancelledError:
        print("Latency check was cancelled")
        raise


async def main():
    # 创建一个display对象，实际应用中可能需要更复杂的实现
    display = AsyncioDisplay()
    
    # 模拟原始代码的运行方式，运行latency检查2秒
    await check_latency(display=display, duration=2)


if __name__ == '__main__':
    asyncio.run(main())