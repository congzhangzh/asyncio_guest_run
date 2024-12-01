#Tips this does not work, just as note here

# refs: https://github.com/libuv/libuv/blob/v1.x/src/unix/core.c
# int uv_backend_timeout(const uv_loop_t* loop) {
#   if (loop->stop_flag != 0)
#     return 0;

#   if (!uv__has_active_handles(loop) && !uv__has_active_reqs(loop))
#     return 0;

#   if (!QUEUE_EMPTY(&loop->idle_handles))
#     return 0;

#   if (!QUEUE_EMPTY(&loop->pending_queue))
#     return 0;

#   if (loop->closing_handles)
#     return 0;

#   return uv__next_timeout(loop);
# }

# **why it does not work for us**
#   1. for us, there has no active handles and requests, so it always return 0
#        if (!uv__has_active_handles(loop) && !uv__has_active_reqs(loop))
#           return 0;
#   2. we will do it later, so this assumption is not correct

def _poll_timeout(self):
    """返回距离下一个定时器触发的时间（毫秒）
    
    返回值:
        -1: 没有定时器，可以无限等待
        0: 有定时器已经到期
        >0: 距离下一个定时器触发的毫秒数
    """
    if self._stopping:
        return 0
    
    # 检查是否有活跃的定时器
    if not self._timers:
        return -1  # 无限等待
        
    # 获取最早的定时器
    next_timer = min(self._timers)
    now = self.time()
    
    if next_timer <= now:
        return 0  # 立即触发
        
    # 计算时间差（毫秒）
    diff = next_timer - now
    return min(diff * 1000, 86400000)  # 最多等待24小时
