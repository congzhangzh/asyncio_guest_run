import asyncio

async def main():
   counter=0
   while counter < 5:
       result = await asyncio.get_event_loop().getaddrinfo('www.mozilla.org', 80)
       print(f"DNS result (1/{len(result)}): {result[0][4]}")  # 打印第一个地址
       await asyncio.sleep(4)
       counter += 1

if __name__ == "__main__":
    asyncio.run(main())
