import flet as ft
import asyncio

async def test():
    print(f"Page.update is coroutine function: {asyncio.iscoroutinefunction(ft.Page.update)}")
    # We can't easily call it without a real session, but we can check the class
    
    col = ft.Column()
    print(f"Column.update is coroutine function: {asyncio.iscoroutinefunction(col.update)}")

if __name__ == "__main__":
    asyncio.run(test())
