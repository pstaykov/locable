import json
import re
import sys
from pathlib import Path
from typing import List, Dict

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from locable.rag.vectorstore import LocalVectorStore

TEMPLATE_ROOT = ROOT / "data" / "templates"
CHUNK_DIR = ROOT / "data" / "chunks"
CHUNK_DIR.mkdir(parents=True, exist_ok=True)
CHUNK_PATH = CHUNK_DIR / "templates.json"

TEMPLATE_DESCRIPTIONS: Dict[str, str] = {
    "startbootstrap-blog-post-gh-pages": "Blog post layout with header image, article body, comments, and sidebar widgets.",
    "startbootstrap-business-frontpage-gh-pages": "Business landing page with hero, callouts, feature cards, and testimonials.",
    "startbootstrap-coming-soon-gh-pages": "Coming soon page with countdown, email signup, and background media.",
    "startbootstrap-creative-gh-pages": "One-page agency/creative theme with hero, services, portfolio, and CTA sections.",
    "startbootstrap-full-width-pics-gh-pages": "Full-width image hero and alternating feature blocks for marketing stories.",
    "startbootstrap-heroic-features-gh-pages": "Simple marketing hero with CTA and a grid of feature cards.",
    "startbootstrap-one-page-wonder-gh-pages": "Scrolling one-page narrative with large imagery and CTA blocks.",
    "startbootstrap-personal-gh-pages": "Personal portfolio with about, projects, and contact pages plus navigation.",
    "startbootstrap-resume-gh-pages": "Resume/CV single-page timeline with skills, experience, and education.",
    "startbootstrap-sb-admin-gh-pages": "Admin dashboard with sidebar, cards, charts, tables, and auth screens.",
    "startbootstrap-shop-homepage-gh-pages": "Storefront homepage showing featured and grid product cards.",
    "startbootstrap-shop-item-gh-pages": "Product detail page with gallery, pricing, and reviews.",
    "startbootstrap-small-business-gh-pages": "Small business landing with hero, call-to-action, contact, and content blocks.",
    "startbootstrap-stylish-portfolio-gh-pages": "Portfolio/agency theme with off-canvas navigation and alternating showcase sections.",
}


def chunk_text(text: str, size: int = 900, overlap: int = 120) -> List[str]:
    chunks: List[str] = []
    if size <= 0:
        return chunks
    start = 0
    text_len = len(text)
    while start < text_len:
        end = min(start + size, text_len)
        chunks.append(text[start:end])
        if end == text_len:
            break
        start = max(0, end - overlap)
    return chunks


def clean_html(text: str) -> str:
    # Strip scripts/styles for cleaner grounding but keep structure text
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def clean_css(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def build_chunks() -> List[Dict]:
    all_chunks: List[Dict] = []
    for template_dir in TEMPLATE_ROOT.iterdir():
        if not template_dir.is_dir():
            continue
        template_name = template_dir.name
        description = TEMPLATE_DESCRIPTIONS.get(template_name, "Bootstrap template")

        # description embedding entry
        all_chunks.append({
            "id": f"{template_name}::description",
            "text": description,
            "metadata": {
                "template": template_name,
                "type": "description",
                "description": description,
                "source": str(template_dir.relative_to(ROOT)),
            },
        })

        # HTML files
        for html_file in template_dir.rglob("*.html"):
            try:
                raw = html_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                raw = ""
            if not raw:
                continue
            cleaned = clean_html(raw)
            for idx, chunk in enumerate(chunk_text(cleaned)):
                all_chunks.append({
                    "id": f"{template_name}::{html_file.name}::html::{idx}",
                    "text": chunk,
                    "metadata": {
                        "template": template_name,
                        "type": "html",
                        "source": str(html_file.relative_to(ROOT)),
                        "description": description,
                        "chunk_index": idx,
                    },
                })

        # CSS files
        for css_file in template_dir.rglob("*.css"):
            try:
                raw = css_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                raw = ""
            if not raw:
                continue
            cleaned = clean_css(raw)
            for idx, chunk in enumerate(chunk_text(cleaned, size=800, overlap=80)):
                all_chunks.append({
                    "id": f"{template_name}::{css_file.name}::css::{idx}",
                    "text": chunk,
                    "metadata": {
                        "template": template_name,
                        "type": "css",
                        "source": str(css_file.relative_to(ROOT)),
                        "description": description,
                        "chunk_index": idx,
                    },
                })
    return all_chunks


def main():
    chunks = build_chunks()
    CHUNK_PATH.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(chunks)} chunks to {CHUNK_PATH}")

    store = LocalVectorStore(persist_dir=str(ROOT / "data" / "chroma"), collection_name="bootstrap")
    count = store.build_index(str(CHUNK_PATH))
    print(f"Indexed {count} chunks into Chroma")


if __name__ == "__main__":
    main()
