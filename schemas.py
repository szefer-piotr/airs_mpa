from pydantic import BaseModel
from typing import Dict

class DataSummary(BaseModel):
    column_name: str
    description: str
    type: str
    unique_value_count: int


class DatasetSummary(BaseModel):
    columns: Dict[str, DataSummary]


schema_payload = {
    "name": "summary_schema",
    "schema": DatasetSummary.model_json_schema(),
}
response_format = {"type": "json_schema", "json_schema": schema_payload}


# ---- Chat response schemas (unchanged) --------------------------------------
hypotheses_schema = {
    "format": {
        "type": "json_schema",
        "name": "hypotheses",
        "schema": {
            "type": "object",
            "properties": {
                "assistant_response": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "hypothesis_refined_with_data_text": {"type": "string"},
                            "refined_hypothesis_text": {"type": "string"},
                        },
                        "required": [
                            "title",
                            "hypothesis_refined_with_data_text",
                            "refined_hypothesis_text",
                        ],
                        "additionalProperties": False,
                    },
                },
                "refined_hypothesis_text": {"type": "string"},
            },
            "required": ["assistant_response", "refined_hypothesis_text"],
            "additionalProperties": False,
        },
        "strict": True,
    }
}

hyp_refining_chat_response_schema = {
    "format": {
        "type": "json_schema",
        "name": "hypothesis",
        "schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "assistant_response": {"type": "string"},
                "refined_hypothesis_text": {"type": "string"},
            },
            "required": ["title", "assistant_response", "refined_hypothesis_text"],
            "additionalProperties": False,
        },
        "strict": True,
    }
}

plan_generation_response_schema = {
    "format": {
        "type": "json_schema",
        "name": "plan_generation_response",
        "schema": {
            "type": "object",
            "properties": {
                "assistant_response": {"type": "string"},
                "current_plan_execution": {"type": "string"},
            },
            "required": ["assistant_response", "current_plan_execution"],
            "additionalProperties": False,
        },
        "strict": True,
    }
}