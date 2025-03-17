#
# Copyright 2020 Richard J. Sheridan
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

# ---begin--- hook helper
import sys
from importlib.util import spec_from_file_location, module_from_spec
import os

#TODO this does not work?
os.environ['PYTHONASYNCIODEBUG'] = '1'

class SimpleFinder:
    def __init__(self, overrides):
        # overrides 是一个字典，key是模块名，value是替换文件的路径
        self.overrides = overrides
    
    # 新的导入协议方法
    def find_spec(self, fullname, path, target=None):
        if fullname in self.overrides:
            print(f"[SimpleFinder] find_spec: {fullname}")
            path = self.overrides[fullname]
            spec = spec_from_file_location(fullname, path)
            return spec
        return None

# 使用方法
patch_dir = os.path.join(os.path.dirname(__file__), 'patches')  # 你的补丁目录
overrides = {
    #'asyncio.windows_events': os.path.join(patch_dir, 'windows_events.py'),
    'asyncio.base_events': os.path.join(patch_dir, 'base_events_patched.py'),
    'amodule': os.path.join(patch_dir, 'amodule_patched.py'),
}

# 安装 finder（需要在任何 asyncio 导入之前）
sys.meta_path.insert(0, SimpleFinder(overrides))
# ---end--- hook helper

import amodule
amodule.say_hello()

import traceback
from queue import Queue

import win32api
import win32con
import win32gui
import win32ui
from outcome import Error
from pywin.mfc import dialog

#import example_tasks
import example_tasks_asyncio

import asyncio_guest_run

TRIO_MSG = win32con.WM_APP + 3

# 使用线程安全的 Queue 代替 deque
trio_functions = Queue()

def do_trio():
    """Process all pending trio tasks in the queue"""
    while not trio_functions.empty():
        try:
            # 获取并执行一个任务
            func = trio_functions.get()
            func()
        except Exception as e:
            print(rf"{__file__}:{do_trio.__name__} e: {e}")
            print(traceback.format_exc())
            raise e

class Win32Host:
    def __init__(self, display):
        self.display = display
        self.mainthreadid = win32api.GetCurrentThreadId()
        # create event queue with null op
        win32gui.PeekMessage(
            win32con.NULL, win32con.WM_USER, win32con.WM_USER, win32con.PM_NOREMOVE
        )
        self.create_message_window()

    def create_message_window(self):
        # 注册窗口类
        wc = win32gui.WNDCLASS()
        wc.lpfnWndProc = self.trio_wndproc_func
        wc.lpszClassName = "TrioMessageWindow"
        win32gui.RegisterClass(wc)
        
        # 创建隐藏窗口
        self.msg_hwnd = win32gui.CreateWindowEx(
            0, "TrioMessageWindow", "Trio Message Window",
            0, 0, 0, 0, 0, 0, 0, None, None
        )

    def trio_wndproc_func(self, hwnd, msg, wparam, lparam):
        if msg == TRIO_MSG:
            # 处理所有排队的 trio 任务
            do_trio()
            return 0
        # elif msg == DESTROY_WINDOW_MSG:
        #     # 在正确的线程中销毁窗口
        #     win32gui.DestroyWindow(hwnd)
        #     return 0
        else:
            return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def run_sync_soon_threadsafe(self, func):
        """先添加函数到队列，后发送消息"""
        trio_functions.put(func)
        win32api.PostMessage(self.msg_hwnd, TRIO_MSG, 0, 0)

    def run_sync_soon_not_threadsafe(self, func):
        """与 threadsafe 相同，保持一致性"""
        trio_functions.put(func)
        win32api.PostMessage(self.msg_hwnd, TRIO_MSG, 0, 0)

    def done_callback(self, outcome):
        """non-blocking request to end the main loop"""
        print(f"Outcome: {outcome}")
        if isinstance(outcome, Error):
            exc = outcome.error
            traceback.print_exception(type(exc), exc, exc.__traceback__)
            exitcode = 1
        else:
            exitcode = 0
        self.display.dialog.PostMessage(win32con.WM_CLOSE, 0, 0)
        self.display.dialog.close()
        # 通过消息请求主线程销毁窗口
        # win32api.PostMessage(self.msg_hwnd, DESTROY_WINDOW_MSG, 0, 0)
        win32gui.PostQuitMessage(exitcode)

    def mainloop(self):
        while True:
            code, msg = win32gui.GetMessage(0, 0, 0)
            if not code:
                break
            if code < 0:
                error = win32api.GetLastError()
                raise RuntimeError(error)

            # 处理标准窗口消息
            win32gui.TranslateMessage(msg)
            win32gui.DispatchMessage(msg)
            # 注意：不再在这里处理 trio 任务
            # 所有 trio 任务由窗口过程中的 do_trio() 处理
            # do_trio()?

def MakeDlgTemplate():
    style = (
        win32con.DS_MODALFRAME
        | win32con.WS_POPUP
        | win32con.WS_VISIBLE
        | win32con.WS_CAPTION
        | win32con.WS_SYSMENU
        | win32con.DS_SETFONT
    )
    cs = win32con.WS_CHILD | win32con.WS_VISIBLE

    w = 300
    h = 21

    dlg = [
        ["...", (0, 0, w, h), style, None, (8, "MS Sans Serif")],
    ]

    s = win32con.WS_TABSTOP | cs

    dlg.append(
        [128, "Cancel", win32con.IDCANCEL, (w - 60, h - 18, 50, 14), s | win32con.BS_PUSHBUTTON]
    )

    return dlg

class PBarDialog(dialog.Dialog):
    def OnInitDialog(self):
        code = super().OnInitDialog()
        self.pbar = win32ui.CreateProgressCtrl()
        self.pbar.CreateWindow(
            win32con.WS_CHILD | win32con.WS_VISIBLE, (10, 10, 310, 24), self, 3000
        )
        return code

    def OnCancel(self):
        # also window close response
        self.cancelfn()

class Win32Display:
    def __init__(self):
        self.dialog = PBarDialog(MakeDlgTemplate())
        self.dialog.CreateWindow()
        # self.display.DoModal()

    def set_title(self, title):
        self.dialog.SetWindowText(title)

    def set_max(self, maximum):
        # hack around uint16 issue
        self.realmax = maximum
        self.dialog.pbar.SetRange(0, 65535)

    def set_value(self, downloaded):
        self.dialog.pbar.SetPos(int((downloaded / self.realmax * 65535)))

    def set_cancel(self, fn):
        self.dialog.cancelfn = fn

def main(task):
    display = Win32Display()
    host = Win32Host(display)
    #trio.lowlevel.start_guest_run
    asyncio_guest_run.asyncio_guest_run(
        task,
        display,
        run_sync_soon_threadsafe=host.run_sync_soon_threadsafe,
        run_sync_soon_not_threadsafe=host.run_sync_soon_not_threadsafe,
        done_callback=host.done_callback,
    )
    host.mainloop()


if __name__ == "__main__":
    import tracemalloc
    tracemalloc.start()
    # 移除警告，问题已修复
    # print("Known bug: Dragging the window freezes everything.")
    # print("For now only click buttons!")
    main(example_tasks_asyncio.count)
