# I Hope:
1. Let's fix https://github.com/congzhangzh/webview_python/issues/1
2. make all the sample work for asyncio with no or less change: https://github.com/richardsheridan/trio-guest/
3. add asyncio.guest_run to python standard library, which api compatible with trio.lowlevel.start_guest_run: https://trio.readthedocs.io/en/stable/reference-lowlevel.html#trio.lowlevel.start_guest_run
```python
    asyncio.guest_run(
        coroutine,
        *coroutine_args,
        run_sync_soon_threadsafe,
        run_sync_soon_not_threadsafe, # will not be implemented in first version
        done_callback
    )
```
## internal
1. make asyncio split pull events and run once
    _run_once: https://github.com/python/cpython/blob/ad9d059eb10ef132edd73075fa6d8d96d95b8701/Lib/asyncio/base_events.py#L1953
    poll in _run_once:
    https://github.com/python/cpython/blob/ad9d059eb10ef132edd73075fa6d8d96d95b8701/Lib/asyncio/base_events.py#L1995
    process ready events in _run_once:
    https://github.com/python/cpython/blob/ad9d059eb10ef132edd73075fa6d8d96d95b8701/Lib/asyncio/base_events.py#L2017
2. extend asyncio with new state like: running,not_running,guest_runnning? 
3. make time/sleep stuff work with guest mode

# The Plan:
1. Base on trio guest mode sample (win 32 + trio asyncio), https://github.com/richardsheridan/trio-guest/blob/master/trio_guest_win32.py
2. incrementally migrate the code to asyncio, minor adjust it
    1. pull event from asyncio
    2. push to gui event loop
    3. repeat
3. the thing will be trouble
    1. running loop detect for many part of asyncio, in the future, asyncio maybe need more state category, like "running loop", "stopped loop", "guest loop"
    2. timer problem? we have deal with it in v1, should be possible to solve it in the same way

# TBD-Cross thread communication
1. do we need Semaphore/Lock?
2. how to use it correctly?
