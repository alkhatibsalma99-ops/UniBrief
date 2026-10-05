import json
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


def extract_requirements_with_ai(text: str) -> dict:
    response = client.responses.create(
        model="gpt-5.6-luna",

        input=f"""
You are analyzing a university assignment.

Extract only concrete requirements that the student must fulfill.

Rules:
- Do not invent requirements.
- Ignore general explanatory text.
- Use the same language as the document.
- Create a short title for each requirement.
- Give each requirement a priority:
  high, medium, or low.

Document:
{text}
""",

        text={
            "format": {
                "type": "json_schema",
                "name": "requirements_result",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "requirements": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {
                                        "type": "string"
                                    },
                                    "description": {
                                        "type": "string"
                                    },
                                    "priority": {
                                        "type": "string",
                                        "enum": [
                                            "high",
                                            "medium",
                                            "low"
                                        ]
                                    }
                                },
                                "required": [
                                    "title",
                                    "description",
                                    "priority"
                                ],
                                "additionalProperties": False
                            }
                        }
                    },
                    "required": [
                        "requirements"
                    ],
                    "additionalProperties": False
                }
            }
        }
    )

    return json.loads(response.output_text)
def check_submission_with_ai(
    submission_text: str,
    requirements: list,
) -> dict:

    requirements_text = "\n".join(
        [
            f"""
Requirement ID: {requirement['id']}
Title: {requirement['title']}
Description: {requirement['description']}
Priority: {requirement['priority']}
"""
            for requirement in requirements
        ]
    )

    response = client.responses.create(
        model="gpt-5.6-luna",

        input=f"""
You are reviewing a student's project submission.

Compare the submission with every requirement.

For each requirement decide:

- fulfilled
- missing
- unclear

Rules:
- Do not invent evidence.
- Only use information found in the submission.
- Give a short explanation.
- Keep the original requirement_id.

Requirements:
{requirements_text}

Submission:
{submission_text}
""",

        text={
            "format": {
                "type": "json_schema",
                "name": "submission_check",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "results": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "requirement_id": {
                                        "type": "integer"
                                    },
                                    "status": {
                                        "type": "string",
                                        "enum": [
                                            "fulfilled",
                                            "missing",
                                            "unclear"
                                        ]
                                    },
                                    "feedback": {
                                        "type": "string"
                                    }
                                },
                                "required": [
                                    "requirement_id",
                                    "status",
                                    "feedback"
                                ],
                                "additionalProperties": False
                            }
                        }
                    },
                    "required": ["results"],
                    "additionalProperties": False
                }
            }
        }
    )

    return json.loads(response.output_text)    