import threading
import time
from enum import Enum
from typing import Optional, Callable, Dict
from queue import Queue
import queue
import logging
from qwen_agent.log import logger


class ConflictStrategy(Enum):
    DISCARD = "discard"
    QUEUE = "queue"
    FORCE = "force"  # TODO: Implement force strategy


class TaskRequest:
    def __init__(self, action: Callable, result: dict, callback=None):
        self.action = action
        self.result = result
        self.callback = callback
        self.timestamp = time.time()
        self.event = threading.Event()
        self.cancellation = threading.Event()
        self.id = f"req_{int(self.timestamp * 1000)}"


class TaskManager:
    def __init__(self, strategy: ConflictStrategy = ConflictStrategy.QUEUE):
        self.strategy = strategy
        self.current_request: Optional[TaskRequest] = None
        self.request_queue = Queue()
        self.working = False
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.worker_thread = None
        self._start_worker()

    def _start_worker(self):
        """start the worker thread for processing requests"""
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()

    def _worker_loop(self):
        """worker loop to process movement requests"""
        while not self.stop_event.is_set():
            try:
                request = self.request_queue.get(timeout=0.1)
                self._execute_request(request)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"TaskManager worker error: {e}")

    def _execute_request(self, request: TaskRequest):
        """process a single movement request"""
        with self.lock:
            self.current_request = request
            self.working = True

        try:
            logger.info(f"Executing request: {request.id}")
            request.result['ret_val'] = request.action(request.cancellation)
        except Exception as e:
            logger.error(f"Error executing request {request.id}: {e}")
        finally:
            with self.lock:
                self.current_request = None
                self.working = False
            request.event.set()

    def submit_request(self, action: Callable, result: dict, callback: Optional[Callable] = None) -> str:
        """submit a request and handle conflicts"""
        request = TaskRequest(action, result, callback)

        with self.lock:
            if self.working:
                return self._handle_conflict(request)
            else:
                self.request_queue.put(request)
                logger.info(f"Request {request.id} queued")
                return request.event

    def _handle_conflict(self, new_request: TaskRequest) -> str:
        """handle conflicts based on the current strategy"""
        if self.strategy == ConflictStrategy.DISCARD:
            logger.info(f"Discarding request {new_request.id} due to conflict")
            return None

        elif self.strategy == ConflictStrategy.QUEUE:
            self.request_queue.put(new_request)
            logger.info(f"Queuing request {new_request.id}")
            return new_request.event

        elif self.strategy == ConflictStrategy.FORCE:
            logger.info(f"Force executing request {new_request.id}")
            self._force_stop_current()
            self.request_queue.put(new_request)
            return new_request.event

    def _force_stop_current(self):
        """Force stop the current request if any."""
        logger.info(f"Force stopping current request: {self.current_request.id}")
        self.current_request.cancellation.set()

    def set_strategy(self, strategy: ConflictStrategy):
        """set the conflict resolution strategy"""
        with self.lock:
            self.strategy = strategy
            logger.info(f"Strategy changed to: {strategy.value}")

    def get_status(self) -> dict:
        """get the current status of the manager"""
        with self.lock:
            return {
                "working": self.working,
                "current_request": self.current_request.id if self.current_request else None,
                "queue_size": self.request_queue.qsize(),
                "strategy": self.strategy.value
            }

    def clear_queue(self):
        """Clear the request queue"""
        with self.lock:
            while not self.request_queue.empty():
                try:
                    self.request_queue.get_nowait()
                except:
                    break
            logger.info("Request queue cleared")

    def shutdown(self):
        """shutdown the manager entirely"""
        self.stop_event.set()
        if self.worker_thread:
            self.worker_thread.join(timeout=5)
        logger.info("TaskManager shutdown")


# Global dictionary to store task manager instances
_task_managers: Dict[str, TaskManager] = {}
_task_managers_mutex = threading.Lock()


def get_task_manager(task_type: str, strategy: ConflictStrategy = ConflictStrategy.QUEUE) -> TaskManager:
    """
    Get or create a TaskManager instance for the given task type.
    This function is thread-safe and maintains singleton instances per task type.

    Args:
        task_type: The type of task (e.g., 'movement', 'camera', 'navigation')
        strategy: The conflict resolution strategy to use for new instances

    Returns:
        TaskManager: The singleton TaskManager instance for the given task type
    """
    with _task_managers_mutex:
        if task_type not in _task_managers:
            logger.info(f"Creating new TaskManager for task type: {task_type}")
            _task_managers[task_type] = TaskManager(strategy)
        _task_managers[task_type].set_strategy(strategy)
        return _task_managers[task_type]
