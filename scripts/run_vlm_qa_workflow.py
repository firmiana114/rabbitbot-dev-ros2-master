from __future__ import annotations

import asyncio
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rabbitbot.agno_agents.vlm_qa_workflow import build_parser, main


if __name__ == "__main__":
    parser = build_parser()
    asyncio.run(main(parser.parse_args()))
