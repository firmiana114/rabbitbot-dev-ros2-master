
from collections import deque
from typing import Iterable, Tuple, Any


class ChatQueue:
    def __init__(self, max_len: int):
        if max_len <= 0:
            raise ValueError("max_len 必须为正整数")
        self._dq = deque(maxlen=max_len)

    def put(self, text, role):
        item  = f"{role}：“{text}“"
        self._dq.append(item)
    
    def build_history(self, max_count=None):
        if max_count is None or max_count > len(self._dq):
            max_count = len(self._dq)

        chat_text = ""
        i = -max_count
        while i < 0:
            chat_text +=  f"{self._dq[i]}\n"
            i += 1
        return chat_text

    def __len__(self):
        return len(self._dq)

    def __repr__(self):
        return f"ChatQueue({list(self._dq)})"
