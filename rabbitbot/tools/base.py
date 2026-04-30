from qwen_agent.tools.base import BaseToolWithFileAccess
import threading

from typing import Optional, Dict, Union, List
from abc import ABC, abstractmethod


class BaseAsyncToolWithFileAccess(BaseToolWithFileAccess, ABC):

    def __init__(self, cfg: Optional[Dict] = None):
        super().__init__(cfg)
        self.stop_signal = threading.Event()
        self.return_value = {'ret_val': None}
        self.worker_thread = None

    @abstractmethod
    def _call(self, params: dict, stop_signal: threading.Event, return_value: dict) -> str:
        raise NotImplementedError

    @abstractmethod
    def _get_running_repr(self, params: dict) -> str:
        raise NotImplementedError
    
    def call(self, params: Union[str, dict], files: List[str] = None, **kwargs) -> str:
        super().call(params, files, **kwargs)
        self._clear()
        params = self._verify_json_format_args(params)
        self.worker_thread = threading.Thread(target=self._call, args=(params, self.stop_signal, self.return_value))
        self.worker_thread.run()
        return self._get_running_repr(params)

    def stop(self):
        self.stop_signal.set()
        self.worker_thread.join()

    def _clear(self):
        self.stop_signal.clear()
        self.return_value['ret_val'] = None

    def get_ret_val(self) -> str:
        return self.return_value['ret_val']
