# 本项目旨在解决 Python 中 Tkinter GUI 与 Asyncio 事件循环的集成问题。

[Python 社区讨论](https://discuss.python.org/t/connecting-asyncio-and-tkinter-event-loops/14722/1)

1. Make asyncio event loop (test with uvloop) work with tkinter gui event loop, the other gui event loop should work as well, like QT/Win32/GTK/etc.
2. In the future, offical Python asyncio event loop should support peek too？which make pull/test from backend thread and run on main thread possible, which is essential for mix tkinter and asyncio.
3. the core concept is inspired by electron, run uv loop in backend thread, and wake up main thread to process events.

## 技术方案

1. **测试场景设计**
   - 创建基础 Tkinter GUI 程序
   - 实现触发异步操作的界面组件
   - 模拟长时间运行的异步任务

2. **事件循环优化**
   - 使用 uvloop 替换默认的事件循环
   - 提升异步操作性能

3. **后台处理机制**
   - 在独立线程中运行 uvloop
   - 实现事件监听和消息队列
   - 处理异步操作结果

4. **UI 更新机制**
   - 使用 Tkinter 的 after 方法安排更新
   - 实现 uvloop.run_once() 的定期执行
   - 确保 UI 响应性

5. **线程同步机制**
   - 实现线程间安全通信
   - 使用信号量控制资源访问
   - 实现互斥锁保护共享资源

## 依赖要求

详见 `requirements.txt`

## [可选] VS Code Remote调试技巧
依赖MobaXterm等的X Server?
1. login to server with ssh X forwarding
2. remote debug with VS Code on local machine
```bash
export DISPLAY=:10.0
```

# 使用uvloop本地版本验证
issue: https://github.com/MagicStack/uvloop/issues/648

```bash
    git clone https://github.com/congzhangzh/uvloop
    pip install -e .
    # Loop when some pyx changed
    python setup.py build_ext --inplace
    # test
    python -c "from uvloop import Loop ; l=Loop() ; print(l)"
```

## 编译加速
```bash
sudo apt install ccache mold   # for Debian/Ubuntu, included in most Linux distros
export CC="ccache gcc"         # add to your .profile
export CXX="ccache g++"        # add to your .profile
export LDFLAGS="-fuse-ld=mold" # add to your .profile
```

## cython调试
```bash
#refs:
# https://cython.readthedocs.io/en/latest/src/userguide/source_files_and_compilation.html#compiler-directives
# https://cython.readthedocs.io/en/latest/src/userguide/debugging.html
# TBD
export CFLAGS="-O0 -g3 -fno-omit-frame-pointer -fno-inline"
export CYTHON_COMPILER_DIRECTIVES="binding=True,language_level=3,linetrace=True,profile=True,embedsignature=True"
export CYTHON_TRACE=1
export CYTHON_TRACE_NOGIL=1
#python setup.py build_ext --help
python setup.py build_ext --inplace --debug -j$(nproc) --cython-always --use-system-libuv --cython-gdb --cython-gen-pxi --cython-line-directives --cython-annotate \
  -D CYTHON_TRACE -D CYTHON_TRACE_NOGIL # --force 
```

## [WIP] Timer 相关参考
TimerHandle: uvloop/uvloop/cbhandles.{pxd,pyx}
UVHandle: uvloop/uvloop/handles/handle.{pxd,pyx}
UVTimer: uvloop/uvloop/handles/timer.{pxd,pyx}

# 待考虑事项
1. UI线程&后端线程精确协作机制(信号量)
2. 主程序安全退出问题

# References
- https://discuss.python.org/t/connecting-asyncio-and-tkinter-event-loops/14722/1
- https://www.electronjs.org/blog/electron-internals-node-integration
- how to get backend id in uvloop
```bash
grep -nri _get_backend_id uvloop/ tests/
uvloop/loop.pyx:1152:    def _get_backend_id(self):
tests/test_sockets.py:275:        epoll = select.epoll.fromfd(self.loop._get_backend_id())
```
 
- how to pull uv loop event and trigger on main thread in electron
https://github.com/electron/electron/blob/8f00cc9c0e78b95e4de14b9b9e1a7df20935e948/shell/common/node_bindings.cc#L929
```c++
void NodeBindings::EmbedThreadRunner(void* arg) {
  auto* self = static_cast<NodeBindings*>(arg);

  while (true) {
    // Wait for the main loop to deal with events.
    uv_sem_wait(&self->embed_sem_);
    if (self->embed_closed_)
      break;

    // Wait for something to happen in uv loop.
    // Note that the PollEvents() is implemented by derived classes, so when
    // this class is being destructed the PollEvents() would not be available
    // anymore. Because of it we must make sure we only invoke PollEvents()
    // when this class is alive.
    self->PollEvents();
    if (self->embed_closed_)
      break;

    // Deal with event in main thread.
    self->WakeupMainThread();
  }
}
```
- how to wake up main thread in electron and run once uv loop
https://github.com/electron/electron/blob/8f00cc9c0e78b95e4de14b9b9e1a7df20935e948/shell/common/node_bindings.cc#L918
```c++
void NodeBindings::WakeupMainThread() {
  DCHECK(task_runner_);
  task_runner_->PostTask(FROM_HERE, base::BindOnce(&NodeBindings::UvRunOnce,
                                                   weak_factory_.GetWeakPtr()));
}
```
- how to run uv loop once in electron, and signal backend pull thread to wake up
https://github.com/electron/electron/blob/8f00cc9c0e78b95e4de14b9b9e1a7df20935e948/shell/common/node_bindings.cc#L877
```c++
void NodeBindings::UvRunOnce() {
  node::Environment* env = uv_env();

  // When doing navigation without restarting renderer process, it may happen
  // that the node environment is destroyed but the message loop is still there.
  // In this case we should not run uv loop.
  if (!env)
    return;

  v8::HandleScope handle_scope(env->isolate());

  // Enter node context while dealing with uv events.
  v8::Context::Scope context_scope(env->context());

  // Node.js expects `kExplicit` microtasks policy and will run microtasks
  // checkpoints after every call into JavaScript. Since we use a different
  // policy in the renderer - switch to `kExplicit` and then drop back to the
  // previous policy value.
  v8::MicrotaskQueue* microtask_queue = env->context()->GetMicrotaskQueue();
  auto old_policy = microtask_queue->microtasks_policy();
  DCHECK_EQ(microtask_queue->GetMicrotasksScopeDepth(), 0);
  microtask_queue->set_microtasks_policy(v8::MicrotasksPolicy::kExplicit);

  if (browser_env_ != BrowserEnvironment::kBrowser)
    TRACE_EVENT_BEGIN0("devtools.timeline", "FunctionCall");

  // Deal with uv events.
  int r = uv_run(uv_loop_, UV_RUN_NOWAIT);

  if (browser_env_ != BrowserEnvironment::kBrowser)
    TRACE_EVENT_END0("devtools.timeline", "FunctionCall");

  microtask_queue->set_microtasks_policy(old_policy);

  if (r == 0)
    base::RunLoop().QuitWhenIdle();  // Quit from uv.

  // Tell the worker thread to continue polling.
  uv_sem_post(&embed_sem_);
}
```
- how to get uv loop in electron
https://github.com/electron/electron/blob/8f00cc9c0e78b95e4de14b9b9e1a7df20935e948/shell/common/node_bindings.h#L162
```c++
[[nodiscard]] constexpr uv_loop_t* uv_loop() { return uv_loop_; }
```

- what the pool events look like in electron
https://github.com/electron/electron/blob/8f00cc9c0e78b95e4de14b9b9e1a7df20935e948/shell/common/node_bindings_linux.h
```c++
namespace electron {

class NodeBindingsLinux : public NodeBindings {
 public:
  explicit NodeBindingsLinux(BrowserEnvironment browser_env);

 private:
  // NodeBindings
  void PollEvents() override;

  // Epoll to poll for uv's backend fd.
  int epoll_;
};

}  // namespace electron

```
- what the pool events look like in electron under linux
https://github.com/electron/electron/blob/8f00cc9c0e78b95e4de14b9b9e1a7df20935e948/shell/common/node_bindings_linux.cc
```c++
NodeBindingsLinux::NodeBindingsLinux(BrowserEnvironment browser_env)
    : NodeBindings(browser_env), epoll_(epoll_create(1)) {
  auto* const event_loop = uv_loop();

  int backend_fd = uv_backend_fd(event_loop);
  struct epoll_event ev = {0};
  ev.events = EPOLLIN;
  ev.data.fd = backend_fd;
  epoll_ctl(epoll_, EPOLL_CTL_ADD, backend_fd, &ev);
}

void NodeBindingsLinux::PollEvents() {
  auto* const event_loop = uv_loop();

  int timeout = uv_backend_timeout(event_loop);

  // Wait for new libuv events.
  int r;
  do {
    struct epoll_event ev;
    r = epoll_wait(epoll_, &ev, 1, timeout);
  } while (r == -1 && errno == EINTR);
}

// static
std::unique_ptr<NodeBindings> NodeBindings::Create(BrowserEnvironment env) {
  return std::make_unique<NodeBindingsLinux>(env);
}

```
- how to get uv loop in electron under windows
https://github.com/electron/electron/blob/8f00cc9c0e78b95e4de14b9b9e1a7df20935e948/shell/common/node_bindings_win.cc
```c++
NodeBindingsWin::NodeBindingsWin(BrowserEnvironment browser_env)
    : NodeBindings(browser_env) {
  auto* const event_loop = uv_loop();

  // on single-core the io comp port NumberOfConcurrentThreads needs to be 2
  // to avoid cpu pegging likely caused by a busy loop in PollEvents
  if (base::SysInfo::NumberOfProcessors() == 1) {
    // the expectation is the event_loop has just been initialized
    // which makes iocp replacement safe
    CHECK_EQ(0u, event_loop->active_handles);
    CHECK_EQ(0u, event_loop->active_reqs.count);

    if (event_loop->iocp && event_loop->iocp != INVALID_HANDLE_VALUE)
      CloseHandle(event_loop->iocp);
    event_loop->iocp =
        CreateIoCompletionPort(INVALID_HANDLE_VALUE, nullptr, 0, 2);
  }
}

void NodeBindingsWin::PollEvents() {
  auto* const event_loop = uv_loop();

  // If there are other kinds of events pending, uv_backend_timeout will
  // instruct us not to wait.
  DWORD bytes, timeout;
  ULONG_PTR key;
  OVERLAPPED* overlapped;

  timeout = uv_backend_timeout(event_loop);

  GetQueuedCompletionStatus(event_loop->iocp, &bytes, &key, &overlapped,
                            timeout);

  // Give the event back so libuv can deal with it.
  if (overlapped != nullptr)
    PostQueuedCompletionStatus(event_loop->iocp, bytes, key, overlapped);
}

// static
std::unique_ptr<NodeBindings> NodeBindings::Create(BrowserEnvironment env) {
  return std::make_unique<NodeBindingsWin>(env);
}
```
- what the pool events look like in electron under mac
https://github.com/electron/electron/blob/8f00cc9c0e78b95e4de14b9b9e1a7df20935e948/shell/common/node_bindings_mac.cc
```c++
NodeBindingsMac::NodeBindingsMac(BrowserEnvironment browser_env)
    : NodeBindings(browser_env) {}

void NodeBindingsMac::PollEvents() {
  auto* const event_loop = uv_loop();

  struct timeval tv;
  int timeout = uv_backend_timeout(event_loop);
  if (timeout != -1) {
    tv.tv_sec = timeout / 1000;
    tv.tv_usec = (timeout % 1000) * 1000;
  }

  fd_set readset;
  int fd = uv_backend_fd(event_loop);
  FD_ZERO(&readset);
  FD_SET(fd, &readset);

  // Wait for new libuv events.
  int r;
  do {
    r = select(fd + 1, &readset, nullptr, nullptr,
               timeout == -1 ? nullptr : &tv);
  } while (r == -1 && errno == EINTR);
}

// static
std::unique_ptr<NodeBindings> NodeBindings::Create(BrowserEnvironment env) {
  return std::make_unique<NodeBindingsMac>(env);
}
```
- 
https://github.com/electron/electron/blob/8f00cc9c0e78b95e4de14b9b9e1a7df20935e948/shell/common/node_bindings.cc#L840C48-L840C65
```c++
void NodeBindings::StartPolling() {
  // Avoid calling UvRunOnce if the loop is already active,
  // otherwise it can lead to situations were the number of active
  // threads processing on IOCP is greater than the concurrency limit.
  if (initialized_)
    return;

  initialized_ = true;

  // The MessageLoop should have been created, remember the one in main thread.
  task_runner_ = base::SingleThreadTaskRunner::GetCurrentDefault();

  // Run uv loop for once to give the uv__io_poll a chance to add all events.
  UvRunOnce();
}
```
- run all uv loop event before exit in electron?
https://github.com/electron/electron/blob/8f00cc9c0e78b95e4de14b9b9e1a7df20935e948/shell/common/node_bindings.cc#L840
```c++
void NodeBindings::JoinAppCode() {
  // We can only "join" app code to the main thread in the browser process
  if (browser_env_ != BrowserEnvironment::kBrowser) {
    return;
  }

  auto* browser = Browser::Get();
  node::Environment* env = uv_env();

  if (!env)
    return;

  v8::HandleScope handle_scope(env->isolate());
  // Enter node context while dealing with uv events.
  v8::Context::Scope context_scope(env->context());

  // Pump the event loop until we get the signal that the app code has finished
  // loading
  while (!app_code_loaded_ && !browser->is_shutting_down()) {
    int r = uv_run(uv_loop_, UV_RUN_ONCE);
    if (r == 0) {
      base::RunLoop().QuitWhenIdle();  // Quit from uv.
      break;
    }
  }
}
```
- the skeleton of single thread task runner in chromium
https://source.chromium.org/chromium/chromium/src/+/main:base/task/single_thread_task_runner.h
- the official libuv document
https://docs.libuv.org/en/v1.x/index.html
- https://docs.libuv.org/en/v1.x/loop.html#c.uv_run
```
int uv_run(uv_loop_t *loop, uv_run_mode mode)
This function runs the event loop. It will act differently depending on the specified mode:

UV_RUN_DEFAULT: Runs the event loop until there are no more active and referenced handles or requests. Returns non-zero if uv_stop() was called and there are still active handles or requests. Returns zero in all other cases.

UV_RUN_ONCE: Poll for i/o once. Note that this function blocks if there are no pending callbacks. Returns zero when done (no active handles or requests left), or non-zero if more callbacks are expected (meaning you should run the event loop again sometime in the future).

UV_RUN_NOWAIT: Poll for i/o once but don’t block if there are no pending callbacks. Returns zero if done (no active handles or requests left), or non-zero if more callbacks are expected (meaning you should run the event loop again sometime in the future).

uv_run() is not reentrant. It must not be called from a callback.
```
- https://github.com/MagicStack/uvloop/blob/7bb12a174884b2ec8b3162a08564e5fb8a5c6b39/uvloop/loop.pyx#L1366
```python
    def run_forever(self):
        """Run the event loop until stop() is called."""
        self._check_closed()
        mode = uv.UV_RUN_DEFAULT
        if self._stopping:
            # loop.stop() was called right before loop.run_forever().
            # This is how asyncio loop behaves.
            mode = uv.UV_RUN_NOWAIT
        self._set_coroutine_debug(self._debug)
        old_agen_hooks = sys.get_asyncgen_hooks()
        sys.set_asyncgen_hooks(firstiter=self._asyncgen_firstiter_hook,
                               finalizer=self._asyncgen_finalizer_hook)
        try:
            self._run(mode)
        finally:
            self._set_coroutine_debug(False)
            sys.set_asyncgen_hooks(*old_agen_hooks)
```
- https://github.com/MagicStack/uvloop/blob/7bb12a174884b2ec8b3162a08564e5fb8a5c6b39/uvloop/includes/uv.pxd#L205
```cython
    ctypedef enum uv_run_mode:
        UV_RUN_DEFAULT = 0,
        UV_RUN_ONCE,
        UV_RUN_NOWAIT
```
- https://github.com/MagicStack/uvloop/blob/7bb12a174884b2ec8b3162a08564e5fb8a5c6b39/uvloop/loop.pyx#L7 https://github.com/MagicStack/uvloop/blob/7bb12a174884b2ec8b3162a08564e5fb8a5c6b39/uvloop/loop.pyx#L513 https://github.com/MagicStack/uvloop/blob/7bb12a174884b2ec8b3162a08564e5fb8a5c6b39/uvloop/loop.pyx#L500
```cython
  def run_forever(self):
      """Run the event loop until stop() is called."""
      self._check_closed()
      mode = uv.UV_RUN_DEFAULT
      if self._stopping:
          # loop.stop() was called right before loop.run_forever().
          # This is how asyncio loop behaves.
          mode = uv.UV_RUN_NOWAIT
      self._set_coroutine_debug(self._debug)
      old_agen_hooks = sys.get_asyncgen_hooks()
      sys.set_asyncgen_hooks(firstiter=self._asyncgen_firstiter_hook,
                              finalizer=self._asyncgen_finalizer_hook)
      try:
          self._run(mode)
      finally:
          self._set_coroutine_debug(False)
          sys.set_asyncgen_hooks(*old_agen_hooks)
  cdef _run(self, uv.uv_run_mode mode):
      cdef int err

      if self._closed == 1:
          raise RuntimeError('unable to start the loop; it was closed')

      if self._running == 1:
          raise RuntimeError('this event loop is already running.')

      if (aio_get_running_loop is not None and
              aio_get_running_loop() is not None):
          raise RuntimeError(
              'Cannot run the event loop while another loop is running')

      # reset _last_error
      self._last_error = None

      self._thread_id = PyThread_get_thread_ident()
      self._running = 1

      self.handler_check__exec_writes.start()
      self.handler_idle.start()

      self._setup_or_resume_signals()

      if aio_set_running_loop is not None:
          aio_set_running_loop(self)
      try:
          self.__run(mode)
      finally:
          if aio_set_running_loop is not None:
              aio_set_running_loop(None)

          self.handler_check__exec_writes.stop()
          self.handler_idle.stop()

          self._pause_signals()

          self._thread_id = 0
          self._running = 0
          self._stopping = 0

      if self._last_error is not None:
          # The loop was stopped with an error with 'loop._stop(error)' call
          raise self._last_error
          
  cdef __run(self, uv.uv_run_mode mode):
    # Although every UVHandle holds a reference to the loop,
    # we want to do everything to ensure that the loop will
    # never deallocate during the run -- so we do some
    # manual refs management.
    Py_INCREF(self)
    with nogil:
        err = uv.uv_run(self.uvloop, mode)
    Py_DECREF(self)

    if err < 0:
        raise convert_error(err)
```
