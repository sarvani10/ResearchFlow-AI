import os
import json
import google.generativeai as genai
from dotenv import load_dotenv
from .schemas import ResearchPaper, ExtractedInsights

load_dotenv()

EXTRACTION_PROMPT = """
You are an expert biomedical and academic research analyst. Carefully read the following scraped markdown content of a research paper or article.

CRITICAL INSTRUCTION: If the markdown content appears to be a "404 Page Not Found", a "reCAPTCHA" challenge, a login wall, or any other non-research error page, you MUST set the "title" field to exactly "[ERROR] Invalid Page Content" and leave other fields empty.

Extract ALL of the following fields and return them as a single valid JSON object ONLY. No markdown, no code fences, no explanation — just the raw JSON.

JSON Schema:
{{
    "title": "Full title of the paper",
    "authors": ["Author Full Name 1", "Author Full Name 2"],
    "publication_date": "YYYY-MM-DD or approximate year or 'Unknown'",
    "journal": "Journal or publisher name, or 'Unknown'",
    "doi": "DOI string if available else ''",
    "abstract": "2-3 sentence overview of the paper goal and context",
    "full_summary": "A detailed 3-4 paragraph narrative summary in plain English covering the background, methods, results, and conclusions of the paper",
    "insights": {{
        "core_findings": ["Specific finding 1", "Specific finding 2", "Specific finding 3"],
        "methodology": "Clear description of research design, data used, sample size, statistical tests, model types, etc.",
        "limitations": ["Limitation 1", "Limitation 2"],
        "keywords": ["keyword1", "keyword2", "keyword3"],
        "future_work": ["Future direction 1", "Future direction 2"]
    }}
}}

MARKDOWN CONTENT (truncated to 25000 chars):
{content}
"""

GEMINI_MODEL_CANDIDATES = [
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
    "gemini-1.5-flash-latest",
    "gemini-1.5-pro",
    "gemini-1.0-pro",
    "gemini-pro",
]

def find_working_gemini_model() -> str:
    """Find an available model from genai.list_models() without pinging to avoid masking quota errors."""
    try:
        available_models = [m.name.replace("models/", "") for m in genai.list_models()]
        target_priorities = [
            "gemini-2.5-flash-lite",
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-flash-latest"
        ]
        for target in target_priorities:
            if target in available_models:
                return target
    except Exception:
        pass
    return "gemini-2.5-flash-lite"

class InsightExtractor:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        self.ready = bool(api_key and api_key != "your_gemini_api_key_here")
        if self.ready:
            genai.configure(api_key=api_key)
            model_name = find_working_gemini_model()
            self.model = genai.GenerativeModel(model_name)
        else:
            self.model = None

    def extract_paper_details(self, url: str, markdown_content: str) -> ResearchPaper:
        """Parses raw scraped content into a structured ResearchPaper object."""

        if not self.ready:
            return self._error_paper(url, "Gemini API key is missing or invalid.")

        if markdown_content.startswith("ERROR:"):
            return self._error_paper(url, markdown_content)
            
        # Quick heuristic filter for common junk pages
        lower_content = markdown_content.lower()
        if "recaptcha" in lower_content and "verify you are human" in lower_content:
            return self._error_paper(url, "Blocked by reCAPTCHA")
        if "404 page not found" in lower_content or "the requested page is unavailable" in lower_content:
            return self._error_paper(url, "Page Not Found (404)")

        prompt = EXTRACTION_PROMPT.format(content=markdown_content[:25000])

        try:
            response = self.model.generate_content(prompt)
            raw_text = response.text.strip()
            # Strip markdown code fences if model ignored instruction
            if "```" in raw_text:
                # Extract content between first and last code fence
                parts = raw_text.split("```")
                raw_text = parts[1] if len(parts) >= 2 else raw_text
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:]
                raw_text = raw_text.strip()
            data = json.loads(raw_text)

            # Extra safeguard: if the LLM flagged it as an error in the title
            if data.get("title", "").startswith("[ERROR]"):
                return self._error_paper(url, data.get("abstract", "Invalid page content detected by AI."))

            insights_data = data.get("insights", {})
            insights = ExtractedInsights(
                core_findings=insights_data.get("core_findings", []),
                methodology=insights_data.get("methodology", ""),
                limitations=insights_data.get("limitations", []),
                keywords=insights_data.get("keywords", []),
                future_work=insights_data.get("future_work", [])
            )

            return ResearchPaper(
                title=data.get("title", "Unknown Title"),
                authors=data.get("authors", []),
                publication_date=data.get("publication_date", ""),
                journal=data.get("journal", ""),
                doi=data.get("doi", ""),
                url=url,
                abstract=data.get("abstract", ""),
                full_summary=data.get("full_summary", ""),
                insights=insights
            )

        except json.JSONDecodeError as e:
            return self._error_paper(url, f"JSON parse failed: {e}")
        except Exception as e:
            return self._error_paper(url, f"LLM call failed: {e}")

    def _error_paper(self, url: str, reason: str) -> ResearchPaper:
        return ResearchPaper(
            title=f"[ERROR] {url[:60]}",
            url=url,
            abstract=reason,
            full_summary=reason,
            insights=ExtractedInsights(
                core_findings=["Extraction failed"],
                methodology="N/A",
                limitations=["N/A"],
                keywords=[],
                future_work=[]
            )
        )
