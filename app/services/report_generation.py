import anthropic
import json
import os

_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

_PROMPT_TEMPLATE = """You are an expert thyroid oncologist. Generate a comprehensive, professional clinical report based on the following patient and case data.

Patient & Case Data:
{case_json}

Generate a structured clinical report with these sections:
1. **Clinical Summary** — Brief overview of the presentation and key findings
2. **Diagnosis** — Based on histopathological type, staging, and molecular markers
3. **Risk Assessment** — ATA risk stratification and key prognostic factors
4. **Treatment Plan** — Recommended management per current clinical guidelines
5. **Follow-up Recommendations** — Surveillance schedule and monitoring parameters

Use formal medical language appropriate for a clinical record. Be specific, concise, and evidence-based."""


def generate_report(case_data: dict) -> str:
    prompt = _PROMPT_TEMPLATE.format(case_json=json.dumps(case_data, indent=2))
    message = _client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text
