#PEP idea

# **Functional view**
# Loop implement side
    # loop.check_event()
    #   check if there is any event to process
    # loop.run_once()
    #   run all events in the queue
    # loop.process_ready()
    #   process ready events (micro task)
    # loop.process_timers() 
    #   or just use run_once()
    #   trigger all timers
# Gui event loop side
    # hook_micro_task_process(callback)
# New sementic of asyncio running loop
    # running=true or integration_mode=True
    # asyncio.sleep or related coroutine will not raise error when loop is not running (integration mode=True)
    # asyncio.sleep will trigger loop.trigger_timers()

# **Runtime view**
# Poll async io event in a backend thread
    # if new timer is scheduled, backend poll should be break, trigger timer check, end this batch of poll
# Run process_ready in each GetMessage/DispatchMessage loop ticks
# Use semaphore to coordinate between backend thread & ui thread (UI finished, then Backend loop, Then trigger ui, Loop)

# **Lifecyle view**
# Before backend thread start, run once and set semaphore
# [TBD] Before gui loop exit, run once more?

# **Timer specific**
# Libuv implement timer in a special way
    # it will call uv__next_timeout in the libuv run loop, which base on check but not trigger, so no handle/no event
    # the backend_fd poll's time out will base on uv__next_timeout, so when timer is due, timer check has a chance
# Under integration mode, give ui thread a chance to process timer, or, cross thread problem
    # all the stuff should looks like start on ui thread, and callback on ui thread
# When new timer be scheduled, and under integration mode, backend poll should be break and recheck
    # the later schedule timer may be due earlier than the previous one, so recheck is necessary
    # an addition pipe is needed for this purpose

# Bugs:
#   loop.get_backend_timeout() which I implement always return 0, I use 1 second by hard coding, which need fix in the future

# TODO: this just for Linux, MAC & Windows should be different

import tkinter as tk
import asyncio
import uvloop
import threading
import select
import tracemalloc
import os
from asyncio import futures
from functools import wraps

os.environ['PYTHONASYNCIODEBUG'] = '1'

# --begin-- global instance 4 easy concept process
# asyncio loop
current_loop=uvloop.Loop()
current_loop.set_debug(True)

# tkinter root
current_root=None
asyncio.set_event_loop(current_loop)

# wake up backend to poll by new timer
wake_backend_4_timer = None
# --end-- global instance 4 easy concept process

def is_debug():
    return "DEBUG" in os.environ

def ensure_process_ready(func):
    if not asyncio.iscoroutinefunction(func):
        raise Exception("func is not a coroutine function")
    
    @wraps(func)
    def wrapper(*args, **kwargs)->None:
        global current_loop, current_root

        if current_loop is None or current_root is None:
            raise Exception("current loop or root is not set")

        coro = func(*args, **kwargs)
        def process_ready():
            #current_loop.call_soon(current_loop._run_once)
            current_loop.process_ready()
            if is_debug():
                print("process ready")
        #asyncio.create_task(coro)
        current_loop.create_task(coro)
        current_root.after(0, process_ready)

    return wrapper

async def tk_callback(context):
    print(f"{tk_callback.__name__} {context} step 1: dns query")
    result = await asyncio.get_event_loop().getaddrinfo('www.mozilla.org', 80)
    print(f"DNS result (1/{len(result)}): {result[0][4]}")  # 打印第一个地址

    print(f"{tk_callback.__name__} {context} step 2: async sleep ")
    await sleep(current_loop, 1)

def create_tk_app():
    root = tk.Tk()
    root.title("Simple Demo")
    root.geometry("300x200")
    
    label = tk.Label(root, text="Status: Ready")
    label.pack(pady=20)
    
    button = tk.Button(root, text="Click Me", command=lambda: ensure_process_ready(tk_callback)("from button"))
    button.pack(pady=20)
    
    return root

def run_tk(root):
    #TODO why this cause "RuntimeWarning: coroutine 'tk_callback' was never awaited", but tk callback works?
    ensure_process_ready(tk_callback)("by hand")
    root.mainloop()

def sleep(loop, delay):
    future = loop.create_future()
    h = loop.call_later(delay,
                        futures._set_result_unless_cancelled,
                        future, None)
    wake_backend_4_timer()
    return future

def main():
    global current_root, current_loop

    current_root= create_tk_app()
    current_root.after(0, tk_callback, "from ui thread")

    prepare_backend_thread(current_root, current_loop)

    run_tk(current_root)

def prepare_backend_thread(tk_root, loop):
    # 创建信号量用于线程协调
    sem = threading.Semaphore(0)
    # 获取后端文件描述符
    backend_fd = loop._get_backend_id()
    # 创建wake up pipe
    wake_r, wake_w = os.pipe()
    
    # 创建epoll实例
    epoll = select.epoll()
    epoll.register(backend_fd, select.POLLIN)
    epoll.register(wake_r, select.POLLIN)
    
    def run_events_on_ui_thread():
        loop.run_once()
        if is_debug():
            print("sem released")
        sem.release()
    
    def _wake_backend_4_timer():
        os.write(wake_w, b'1')
        if is_debug():
            print("backend thread waked up")
    
    def backend_thread_loop():
        try:
            while True:
                # 等待UI线程处理完成
                sem.acquire()
                is_timeout = False
                while True:
                    #TODO why it's always return 0? 
                    #timeout = loop.get_backend_timeout()
                    timeout=0.5
                    print(f'timeout {timeout}')

                    try:
                        events = epoll.poll(timeout=timeout)
                        for fd, _ in events:
                            if fd == wake_r:
                                is_timeout = True
                                os.read(wake_r, 1)  # 清除唤醒信号
                        break
                    except InterruptedError:
                        continue
                if is_debug():
                    print(f"events: {events}, is_timeout: {is_timeout}")
                tk_root.after(0, run_events_on_ui_thread)
        except Exception as e:
            print(f"Backend thread error: {e}")
        finally:
            epoll.unregister(backend_fd)
            epoll.unregister(wake_r)
            epoll.close()
            os.close(wake_r)
            os.close(wake_w)
    global wake_backend_4_timer
    wake_backend_4_timer = _wake_backend_4_timer

    # 初始运行并释放信号量
    run_events_on_ui_thread()

    # 启动后端线程
    threading.Thread(target=backend_thread_loop, daemon=True).start()
    
if __name__ == "__main__":
    tracemalloc.start()
    main() 
