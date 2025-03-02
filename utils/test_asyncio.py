import asyncio


async def normal_task():
    """普通任务，会被 Ctrl+C 取消"""
    try:
        print("普通任务开始运行...")
        while True:
            print("普通任务正在运行...")
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        print("普通任务被取消了")
        raise
    finally:
        print("普通任务结束")


async def original_task():
    """原始任务，无法修改其内部实现"""
    print("原始任务开始运行...")
    while True:
        print("原始任务正在运行...")
        await asyncio.sleep(1)


async def cancellation_guard(coro):
    """
    包装协程，保护它不被取消
    即使收到取消请求，也会继续运行原始协程
    """
    task = asyncio.create_task(coro)
    try:
        await task
    except asyncio.CancelledError:
        print("包装器收到取消请求，但我们继续等待原始任务")
        # 忽略取消请求，继续等待原始任务
        await task
    finally:
        if not task.done():
            print("包装器结束，但原始任务仍在运行")


async def main():
    # 创建普通任务
    normal = asyncio.create_task(normal_task())

    # 创建受保护任务（使用包装器）
    protected = asyncio.create_task(cancellation_guard(original_task()))

    # 等待任务完成（实际上会一直运行直到被中断）
    try:
        await asyncio.gather(normal, protected)
    except asyncio.CancelledError:
        print("主协程捕获到 CancelledError")
        # 不重新抛出异常，让程序继续运行
        print("等待 3 秒观察任务状态...")
        await asyncio.sleep(3)

        print(f"普通任务状态: {'已取消' if normal.cancelled() else '运行中'}")
        print(f"受保护任务状态: {'已取消' if protected.cancelled() else '运行中'}")


# 手动创建和管理事件循环
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

try:
    loop.run_until_complete(main())
except KeyboardInterrupt:
    print("\n捕获到 KeyboardInterrupt")
    # 获取所有未完成的任务
    tasks = asyncio.all_tasks(loop)
    for task in tasks:
        if not task.done():
            print(f"取消任务: {task}")
            task.cancel()

    # 让循环再运行一会儿，处理取消
    loop.run_until_complete(asyncio.sleep(0.1))
    print("所有任务已取消，但受保护任务可能会忽略取消请求")
finally:
    loop.close()
    print("事件循环已关闭，程序退出")
