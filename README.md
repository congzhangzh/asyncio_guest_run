# Tkinter 与 Asyncio 事件循环集成方案

本项目旨在解决 Python 中 Tkinter GUI 与 Asyncio 事件循环的集成问题。

## 项目目标

解决 [Python 社区讨论](https://discuss.python.org/t/connecting-asyncio-and-tkinter-event-loops/14722/1) 中提出的 Tkinter 与 Asyncio 事件循环集成的挑战。

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
