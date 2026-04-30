from qwen_agent.tools.base import BaseToolWithFileAccess, register_tool
from typing import Union, List


@register_tool('respond')
class Respond(BaseToolWithFileAccess):
    description = '回复用户'
    parameters = [
        {
            'name': 'message',
            'type': 'string',
            'description': '回复内容',
            'required': True
        },
    ]

    def call(self, params: Union[str, dict], files: List[str] = None, **kwargs) -> str:
        super().call(params=params, files=files)
        params = self._verify_json_format_args(params)
        class bcolors:
            HEADER = '\033[95m'
            OKBLUE = '\033[94m'
            OKCYAN = '\033[96m'
            OKGREEN = '\033[92m'
            WARNING = '\033[93m'
            FAIL = '\033[91m'
            ENDC = '\033[0m'
            BOLD = '\033[1m'
            UNDERLINE = '\033[4m'
        print(f'{bcolors.OKGREEN}{params["message"]}{bcolors.ENDC}')
        return '已回复用户'
