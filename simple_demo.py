import tkinter as tk
import asyncio
import uvloop
import threading

# ---- Tkinter 部分 ----
def create_tk_app():
    root = tk.Tk()
    root.title("Simple Demo")
    root.geometry("300x200")
    
    label = tk.Label(root, text="Status: Ready")
    label.pack(pady=20)
    
    button = tk.Button(root, text="Click Me", command=lambda: tk_after_test("from button"))
    button.pack(pady=20)
    
    return root, label, button

def run_tk(root):
    asyncio.ensure_future(dummy_task())
    root.mainloop()

# ---- Asyncio 部分 ----
async def dummy_task():
    print("Starting async task...")
    for i in range(3):
        print(f"Async task step {i}")
        await asyncio.sleep(1)
    print("Async task completed!")

async def run_async():
    uvloop.install()
    await dummy_task()

def tk_after_test(msg):
    print(f"tk after test: {msg}")
    pass

# ---- Main ----
def main():
    # 创建 TK 应用
    root, label, button = create_tk_app()
    
    # 选择运行模式 (取消注释其中之一)
    
    # 模式1: 只运行 TK
    # run_tk(root)
    
    # 模式2: 只运行 Async
    #asyncio.run(run_async())
    
    # 模式3: 都运行（注意：这只是示例，实际上这样运行会阻塞）
    #asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    loop = uvloop.Loop()
    asyncio.set_event_loop(loop)
    #root.after(0, loop.run_until_complete, run_async())
    #loop.run_until_complete(run_async())
    #asyncio.run(run_async())
    root.after(0, tk_after_test, "from ui thread")
    threading.Thread(target=backend_pull_and_trigger, args=(root, loop)).start()
    run_tk(root)

def backend_pull_and_trigger(tk_root, loop):
    #pull event from loop
    #trigger uvloop runonce on tk
    tk_root.after(0, tk_after_test, "from backend thread")
    #loop.run_until_complete(run_async())
    pass

if __name__ == "__main__":
    main() 
