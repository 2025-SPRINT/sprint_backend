import time
import functools
import asyncio
from collections import defaultdict
import threading

class Profiler:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(Profiler, cls).__new__(cls)
                cls._instance.data = defaultdict(lambda: {"total_time": 0, "calls": 0})
        return cls._instance

    def trace(self, name=None):
        """
        Decorator to trace the execution time of a function.
        Supports both sync and async functions.
        """
        def decorator(func):
            func_name = name or f"{func.__module__}.{func.__name__}"
            
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                start = time.perf_counter()
                try:
                    return await func(*args, **kwargs)
                finally:
                    duration = time.perf_counter() - start
                    with self._lock:
                        self.data[func_name]["total_time"] += duration
                        self.data[func_name]["calls"] += 1

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                start = time.perf_counter()
                try:
                    return func(*args, **kwargs)
                finally:
                    duration = time.perf_counter() - start
                    with self._lock:
                        self.data[func_name]["total_time"] += duration
                        self.data[func_name]["calls"] += 1

            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            return sync_wrapper
        return decorator

    def log_manual(self, name, duration):
        """Manually log a duration for a specific component."""
        with self._lock:
            self.data[name]["total_time"] += duration
            self.data[name]["calls"] += 1

    def print_summary(self):
        """Prints a summary table of all recorded timings and clears the data."""
        with self._lock:
            if not self.data:
                print("\n[Profiler] No data recorded.")
                return

            print("\n" + "="*70)
            print(f"{'Performance Bottleneck Analysis':^70}")
            print("-" * 70)
            print(f"{'Component / Function':<45} | {'Calls':<6} | {'Total Time':<12}")
            print("-" * 70)
            
            # Sort by total time descending
            items = sorted(self.data.items(), key=lambda x: x[1]['total_time'], reverse=True)
            
            for name, stats in items:
                print(f"{name:<45} | {stats['calls']:<6} | {stats['total_time']:>10.4f}s")
            
            print("="*70 + "\n")
            self.data.clear()

# Global instance for easy access
profiler = Profiler()
trace = profiler.trace
