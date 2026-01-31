from __future__ import annotations

from dataclasses import dataclass
from typing import Dict
import json


@dataclass
class Tool:
    name: str
    description: str
    input_schema: Dict
    display_name: str

    def schema_str(self, indent: int = 2) -> str:
        return json.dumps(self.input_schema, indent=indent)

    def get_for_system_prompt(self) -> str:
        return f"{self.name}: {self.description}\nArg Schema: {self.schema_str(indent=2)}"
