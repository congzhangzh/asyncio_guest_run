import asyncio
import enum
import sys
import threading
from typing import Union, Callable, Any, Optional, Dict

class GUIMode(str, enum.Enum):
    WIN32 = "win32"
    GTK = "gtk"
    QT = "qt"
    TK = "tk"
    AUTO = "auto"

class GuestModeError(Exception):
    pass

class _GUIBase:
    def __init__(self, embedded: bool = False):
        self.embedded = embedded
        self.loop = asyncio.get_event_loop() if embedded else asyncio.new_event_loop()
        self.stop_event = threading.Event()
        
    def process_events(self):
        #TODO: patch asyncio events.py?
        # https://github.com/python/cpython/blob/main/Lib/asyncio/windows_events.py
        # https://github.com/python/cpython/blob/main/Lib/asyncio/unix_events.py
        self.loop._run_once()
        
    def schedule_soon(self, callback):
        self.loop.call_soon_threadsafe(callback)

class _Win32GUI(_GUIBase):
    def __init__(self, embedded: bool = False):
        super().__init__(embedded)
        import win32gui
        import win32con
        self.win32gui = win32gui
        self.win32con = win32con
        
        if not embedded:
            wc = win32gui.WNDCLASS()
            wc.lpszClassName = "AsyncioGuest"
            wc.lpfnWndProc = self._wndproc
            win32gui.RegisterClass(wc)
            self.hwnd = win32gui.CreateWindow(
                wc.lpszClassName, "", 0, 0, 0, 0, 0, 0, 0, 0, None
            )
    
    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == self.win32con.WM_DESTROY:
            self.stop_event.set()
        return self.win32gui.DefWindowProc(hwnd, msg, wparam, lparam)
    
    def run(self, coro_or_func: Any) -> Optional[Any]:
        if not self.embedded:
            asyncio.set_event_loop(self.loop)
            
        is_coroutine = asyncio.iscoroutine(coro_or_func)
        result = None
        
        try:
            if is_coroutine:
                future = asyncio.ensure_future(coro_or_func, loop=self.loop)
                while not (future.done() or self.stop_event.is_set()):
                    self.win32gui.PumpWaitingMessages()
                    self.process_events()
                result = future.result() if future.done() else None
            else:
                self.schedule_soon(coro_or_func)
                while not self.stop_event.is_set():
                    self.win32gui.PumpWaitingMessages()
                    self.process_events()
        finally:
            if not self.embedded:
                self.win32gui.DestroyWindow(self.hwnd)
                self.loop.close()
                
        return result

class _QtGUI(_GUIBase):
    def __init__(self, embedded: bool = False):
        super().__init__(embedded)
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import QTimer
        
        self.app = QApplication.instance()
        if self.app is None and not embedded:
            self.app = QApplication([])
            
        self.timer = QTimer()
        self.timer.timeout.connect(self.process_events)
        self.timer.start(0)
    
    def run(self, coro_or_func: Any) -> Optional[Any]:
        if not self.embedded:
            asyncio.set_event_loop(self.loop)
            
        is_coroutine = asyncio.iscoroutine(coro_or_func)
        result = None
        
        try:
            if is_coroutine:
                future = asyncio.ensure_future(coro_or_func, loop=self.loop)
                while not future.done():
                    self.app.processEvents()
                result = future.result()
            else:
                self.schedule_soon(coro_or_func)
                if not self.embedded:
                    self.app.exec_()
        finally:
            if not self.embedded:
                self.timer.stop()
                self.loop.close()
                
        return result

class _GtkGUI(_GUIBase):
    def __init__(self, embedded: bool = False):
        super().__init__(embedded)
        import gi
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk, GLib
        self.gtk = Gtk
        self.glib = GLib
        
        if not embedded:
            self.glib.timeout_add(0, self.process_events)
    
    def run(self, coro_or_func: Any) -> Optional[Any]:
        if not self.embedded:
            asyncio.set_event_loop(self.loop)
            
        is_coroutine = asyncio.iscoroutine(coro_or_func)
        result = None
        
        try:
            if is_coroutine:
                future = asyncio.ensure_future(coro_or_func, loop=self.loop)
                while not future.done():
                    self.gtk.main_iteration_do(False)
                result = future.result()
            else:
                self.schedule_soon(coro_or_func)
                if not self.embedded:
                    self.gtk.main()
        finally:
            if not self.embedded:
                self.loop.close()
                
        return result

class _TkGUI(_GUIBase):
    def __init__(self, embedded: bool = False):
        super().__init__(embedded)
        import tkinter as tk
        
        self.root = tk.Tk() if not embedded else None
        if self.root:
            self.root.withdraw()  # 隐藏窗口
            self.root.after(0, self.process_events)
    
    def run(self, coro_or_func: Any) -> Optional[Any]:
        if not self.embedded:
            asyncio.set_event_loop(self.loop)
            
        is_coroutine = asyncio.iscoroutine(coro_or_func)
        result = None
        
        try:
            if is_coroutine:
                future = asyncio.ensure_future(coro_or_func, loop=self.loop)
                while not future.done():
                    self.root.update()
                result = future.result()
            else:
                self.schedule_soon(coro_or_func)
                if not self.embedded:
                    self.root.mainloop()
        finally:
            if not self.embedded:
                self.root.destroy()
                self.loop.close()
                
        return result

def start_guest_mode(
    coro_or_func: Union[Callable, Any],
    mode: Union[str, GUIMode] = "auto",
    *,
    embedded: bool = False
) -> Optional[Any]:
    if isinstance(mode, str):
        mode = GUIMode(mode.lower())

    if mode == GUIMode.AUTO:
        if sys.platform == 'win32':
            try:
                import win32gui
                mode = GUIMode.WIN32
            except ImportError:
                pass
        
        if mode == GUIMode.AUTO:
            for test_mode, module_info in [
                (GUIMode.QT, ('PyQt5.QtWidgets', 'QApplication')),
                (GUIMode.GTK, ('gi.repository', 'Gtk')),
                (GUIMode.TK, ('tkinter', 'Tk'))
            ]:
                try:
                    __import__(module_info[0])
                    mode = test_mode
                    break
                except ImportError:
                    continue

    gui_implementations: Dict[GUIMode, type] = {
        GUIMode.WIN32: _Win32GUI,
        GUIMode.QT: _QtGUI,
        GUIMode.GTK: _GtkGUI,
        GUIMode.TK: _TkGUI
    }

    gui_class = gui_implementations.get(mode)
    if gui_class is None:
        raise GuestModeError(f"No suitable GUI framework found for mode: {mode}")

    try:
        gui = gui_class(embedded=embedded)
        return gui.run(coro_or_func)
    except ImportError as e:
        raise GuestModeError(f"Failed to initialize {mode} framework: {e}")

if __name__ == "__main__":
    # case 1: standalone mode
    async def example_coro():
        print("Starting coroutine")
        await asyncio.sleep(1)
        print("Coroutine completed")
        return "Done!"

    result = start_guest_mode(example_coro())
    print(f"Result: {result}")

    # # case 2: embedded mode
    # from PyQt5.QtWidgets import QApplication
    # import sys

    # app = QApplication(sys.argv)
    
    # async def embedded_coro():
    #     print("Starting embedded coroutine")
    #     await asyncio.sleep(1)
    #     print("Embedded coroutine completed")
    #     app.quit()
    #     return "Embedded done!"

    # result = start_guest_mode(embedded_coro(), mode="qt", embedded=True)
    # app.exec_()
    # print(f"Embedded result: {result}")

    # # case 3: classic mode
    # def example_classic():
    #     async def periodic():
    #         while True:
    #             print("Periodic task")
    #             await asyncio.sleep(1)
        
    #     asyncio.get_event_loop().create_task(periodic())

    # start_guest_mode(example_classic)
