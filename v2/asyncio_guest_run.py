import asyncio
import os
import threading

def is_debug():
    return "DEBUG" in os.environ

def asyncio_guest_run(async_func, *async_func_args, run_sync_soon_threadsafe, run_sync_soon_not_threadsafe, done_callback):
    #asyncio.run(async_func(*async_func_args))
    # 创建信号量用于线程协调
    # import threading
    sem = threading.Semaphore(0)
    # 获取后端文件描述符
    # backend_fd = loop._get_backend_id()
    # # 创建wake up pipe
    # wake_r, wake_w = os.pipe()

    # 创建epoll实例
    # epoll = select.epoll()
    # epoll.register(backend_fd, select.POLLIN)
    # epoll.register(wake_r, select.POLLIN)

    loop=asyncio.new_event_loop()
    loop.set_debug(True)
    asyncio.set_event_loop(loop)

    def process_events_and_ready():
        loop.process_events()
        loop.process_ready()
        if is_debug():
            print("sem released")
        sem.release()

    # def _wake_backend_4_timer():
    #     os.write(wake_w, b'1')
    #     if is_debug():
    #         print("backend thread waked up")

    def backend_thread_loop():
        try:
            while True:
                # 等待UI线程处理完成
                sem.acquire()
                #is_timeout = False
                # while True:
                #     #TODO why it's always return 0? 
                #     timeout = loop.get_backend_timeout()
                #     if is_debug():
                #         print(f'timeout {timeout}')

                #     try:
                #         events = epoll.poll(timeout=timeout)
                #         for fd, _ in events:
                #             if fd == wake_r:
                #                 is_timeout = True
                #                 os.read(wake_r, 1)  # 清除唤醒信号
                #         break
                #     except InterruptedError:
                #         continue
                # if is_debug():
                #     print(f"events: {events}, is_timeout: {is_timeout}")
                # tk_root.after(0, run_events_on_ui_thread)
                loop.poll_events()
                run_sync_soon_threadsafe(process_events_and_ready)
        except Exception as e:
            print(f"Backend thread error: {e}")
        finally:
            # epoll.unregister(backend_fd)
            # epoll.unregister(wake_r)
            # epoll.close()
            # os.close(wake_r)
            # os.close(wake_w)
            pass
    # global wake_backend_4_timer
    # wake_backend_4_timer = _wake_backend_4_timer

    # 初始运行并释放信号量
    process_events_and_ready()

    # 启动后端线程
    threading.Thread(target=backend_thread_loop, daemon=True).start()
