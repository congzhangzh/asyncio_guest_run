import asyncio
import threading

def is_debug():
    return False  # 简化调试输出

def schedule_on_asyncio(coro):
    def schedule_coro():
        loop = asyncio.get_event_loop()
        asyncio.run_coroutine_threadsafe(coro, loop)
    return schedule_coro

def asyncio_guest_run(async_func, *async_func_args, run_sync_soon_threadsafe, run_sync_soon_not_threadsafe, done_callback):
    """最简化的asyncio guest运行函数"""
    # 创建信号量用于线程协调
    sem = threading.Semaphore(0)
    
    # 创建事件循环
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    asyncio._set_running_loop(loop)

    # 修补loop._check_running方法
    # original_check_running = loop._check_running
    # def patched_check_running(self):
    #     # 忽略运行状态检查
    #     raise Exception('patched_check_running')
    #     return
    # loop._check_running = patched_check_running.__get__(loop)
    count = 0
    # UI线程函数
    def process_events_on_ui(events):
        try:
            nonlocal count
            count += 1
            print(f"ui trigger number: {count}")
            if not loop.is_closed():
                # 处理事件和回调
                loop.process_events(events)
                loop.process_ready()
                # 释放信号量让后端线程继续
                sem.release()
        except Exception as e:
            print(rf'{__file__}:{process_events_on_ui.__name__} e: {e}')
            raise  
    # 后端线程函数
    def backend_thread_loop():
        from functools import partial
        try:
            while not loop.is_closed():
                # 等待UI线程处理完成
                sem.acquire()
                
                # 轮询I/O事件
                #loop._last_events = loop.poll_events()
                events = loop.poll_events()
                # 请求UI线程处理事件
                run_sync_soon_threadsafe(partial(process_events_on_ui, events))
        except Exception as e:
            print(f"后端线程错误: {e}")
            run_sync_soon_threadsafe(lambda: done_callback(Exception(str(e))))
    
    # 创建任务
    task = loop.create_task(async_func(*async_func_args))
    
    # 设置完成回调
    def on_task_done(fut):
        try:
            if fut.cancelled():
                run_sync_soon_threadsafe(lambda: done_callback(asyncio.CancelledError()))
            elif fut.exception():
                run_sync_soon_threadsafe(lambda: done_callback(fut.exception()))
            else:
                run_sync_soon_threadsafe(lambda: done_callback(fut.result()))
        except Exception as e:
            run_sync_soon_threadsafe(lambda: done_callback(Exception(str(e))))
    
    task.add_done_callback(on_task_done)
    
    # after create task, ready deque is not empty
    process_events_on_ui([])
    #sem.release()
    
    # 启动后端线程
    threading.Thread(target=backend_thread_loop, daemon=True).start()
    
    return task
