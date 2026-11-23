"""
api/docs.py — Built-In Reference Manual & Editable Custom Documentation API
===========================================================================

Serves all built-in repository Markdown documentation under `docs/` as locked,
read-only reference articles aligned with `zensical.toml`, and provides full
file-backed CRUD for user-created `.md` articles stored in `docs/custom/`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
import tomllib
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(tags=["Documentation"])

ROOT_DIR = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT_DIR / "docs"
CUSTOM_DOCS_DIR = DOCS_DIR / "custom"
ZENSICAL_TOML = ROOT_DIR / "zensical.toml"

VALID_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")
_FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n*", re.DOTALL)


class CustomDocCreateRequest(BaseModel):
    """Payload for creating a new custom `.md` documentation article."""

    title: str
    section: str = "Custom Articles"
    content: str = ""
    slug: Optional[str] = None


class CustomDocUpdateRequest(BaseModel):
    """Payload for updating an existing custom `.md` documentation article."""

    title: str
    section: str = "Custom Articles"
    content: str = ""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9_-]+", "-", text.strip().lower())
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-_")
    if not cleaned:
        return "untitled-note"
    return cleaned[:80]


def _validate_custom_slug(slug: str) -> str:
    candidate = slug.strip().lower()
    if not VALID_SLUG_RE.match(candidate):
        raise HTTPException(
            status_code=400,
            detail="Invalid article slug. Use lowercase letters, numbers, '-' or '_' (max 80 chars).",
        )
    return candidate


def _parse_frontmatter(raw: str) -> Tuple[Dict[str, str], str]:
    match = _FRONTMATTER_RE.match(raw)
    if not match:
        return {}, raw
    meta: Dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        meta[k.strip().lower()] = v.strip()
    body = raw[match.end() :]
    return meta, body


def _serialize_custom_doc(title: str, section: str, content: str, updated_at: str) -> str:
    safe_title = " ".join(title.splitlines()).strip()
    safe_section = " ".join(section.splitlines()).strip() or "Custom Articles"
    body = content.lstrip("\r\n")
    return (
        f"---\n"
        f"title: {safe_title}\n"
        f"section: {safe_section}\n"
        f"updated_at: {updated_at}\n"
        f"---\n\n"
        f"{body}"
    )


def _resolve_builtin_path(doc_id: str) -> Path:
    cleaned = doc_id.strip().lstrip("/")
    if not cleaned or ".." in Path(cleaned).parts or cleaned.startswith("custom/"):
        raise HTTPException(status_code=400, detail=f"Invalid built-in documentation path '{doc_id}'")

    docs_root = DOCS_DIR.resolve()
    target = (docs_root / cleaned).resolve()
    if not target.is_relative_to(docs_root) or target.suffix.lower() != ".md" or not target.is_file():
        raise HTTPException(status_code=404, detail=f"Documentation article '{doc_id}' not found")
    if target.is_relative_to(CUSTOM_DOCS_DIR.resolve()):
        raise HTTPException(status_code=400, detail="Use custom article routes for docs/custom/*")
    return target


def _collect_nav_items(items: Any, section_name: str, out: List[Dict[str, Any]]) -> None:
    if not isinstance(items, list):
        return
    docs_root = DOCS_DIR.resolve()
    for entry in items:
        if not isinstance(entry, dict):
            continue
        for label, target in entry.items():
            if isinstance(target, str):
                candidate = (docs_root / target).resolve()
                if (
                    candidate.is_relative_to(docs_root)
                    and not candidate.is_relative_to(CUSTOM_DOCS_DIR.resolve())
                    and candidate.suffix.lower() == ".md"
                    and candidate.is_file()
                ):
                    rel_id = candidate.relative_to(docs_root).as_posix()
                    out.append({
                        "id": rel_id,
                        "title": str(label),
                        "section": section_name,
                        "locked": True,
                        "source": "builtin",
                    })
            elif isinstance(target, list):
                _collect_nav_items(target, str(label), out)


def _load_builtin_sections() -> List[Dict[str, Any]]:
    sections: List[Dict[str, Any]] = []
    docs_root = DOCS_DIR.resolve()

    if ZENSICAL_TOML.is_file():
        try:
            with open(ZENSICAL_TOML, "rb") as f:
                cfg = tomllib.load(f)
            nav = cfg.get("project", {}).get("nav", [])
            for nav_entry in nav:
                if not isinstance(nav_entry, dict):
                    continue
                for sec_title, val in nav_entry.items():
                    articles: List[Dict[str, Any]] = []
                    if isinstance(val, str):
                        candidate = (docs_root / val).resolve()
                        if candidate.is_relative_to(docs_root) and candidate.is_file():
                            rel_id = candidate.relative_to(docs_root).as_posix()
                            articles.append({
                                "id": rel_id,
                                "title": str(sec_title),
                                "section": str(sec_title),
                                "locked": True,
                                "source": "builtin",
                            })
                    elif isinstance(val, list):
                        _collect_nav_items(val, str(sec_title), articles)
                    if articles:
                        sections.append({"title": str(sec_title), "articles": articles})
            if sections:
                return sections
        except Exception:
            sections = []

    # Fallback filesystem scan if zensical.toml nav could not be parsed
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    if docs_root.is_dir():
        for md_path in sorted(docs_root.rglob("*.md")):
            rel_parts = md_path.relative_to(docs_root).parts
            if rel_parts[0] in ("custom", "_build"):
                continue
            rel_id = md_path.relative_to(docs_root).as_posix()
            sec = "Overview" if len(rel_parts) == 1 else rel_parts[0].replace("_", " ").title()
            title = md_path.stem.replace("_", " ").title()
            grouped.setdefault(sec, []).append({
                "id": rel_id,
                "title": title,
                "section": sec,
                "locked": True,
                "source": "builtin",
            })
    return [{"title": sec, "articles": items} for sec, items in grouped.items()]


def _load_custom_articles() -> List[Dict[str, Any]]:
    if not CUSTOM_DOCS_DIR.is_dir():
        return []
    articles: List[Dict[str, Any]] = []
    for md_path in sorted(CUSTOM_DOCS_DIR.glob("*.md")):
        try:
            raw = md_path.read_text(encoding="utf-8")
        except OSError:
            continue
        meta, body = _parse_frontmatter(raw)
        fallback_title = md_path.stem.replace("-", " ").replace("_", " ").title()
        for line in body.splitlines():
            if line.startswith("# "):
                fallback_title = line[2:].strip()
                break
        mtime_iso = datetime.fromtimestamp(md_path.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        articles.append({
            "id": f"custom/{md_path.stem}",
            "slug": md_path.stem,
            "title": meta.get("title") or fallback_title,
            "section": meta.get("section") or "Custom Articles",
            "locked": False,
            "source": "custom",
            "updated_at": meta.get("updated_at") or mtime_iso,
        })
    return articles


def _find_builtin_meta(doc_id: str) -> Tuple[str, str]:
    for sec in _load_builtin_sections():
        for art in sec.get("articles", []):
            if art.get("id") == doc_id:
                return str(art["title"]), str(art["section"])
    stem = Path(doc_id).stem.replace("_", " ").title()
    return stem, "Reference"


@router.get("/api/docs")
def list_documentation_catalog() -> Dict[str, Any]:
    """Lists locked built-in documentation sections and editable custom Markdown articles."""
    sections = _load_builtin_sections()
    custom_articles = _load_custom_articles()
    builtin_count = sum(len(s.get("articles", [])) for s in sections)
    return {
        "sections": sections,
        "custom_articles": custom_articles,
        "builtin_count": builtin_count,
        "custom_count": len(custom_articles),
        "total": builtin_count + len(custom_articles),
    }


@router.get("/api/docs/article")
def get_documentation_article(id: str) -> Dict[str, Any]:
    """Fetches a built-in (locked) or custom Markdown article by ID."""
    cleaned = id.strip().lstrip("/")
    if cleaned.startswith("custom/"):
        slug = _validate_custom_slug(cleaned[len("custom/") :])
        target = CUSTOM_DOCS_DIR / f"{slug}.md"
        if not target.is_file():
            raise HTTPException(status_code=404, detail=f"Custom article '{slug}' not found")
        raw = target.read_text(encoding="utf-8")
        meta, body = _parse_frontmatter(raw)
        mtime_iso = datetime.fromtimestamp(target.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return {
            "id": f"custom/{slug}",
            "slug": slug,
            "title": meta.get("title") or slug,
            "section": meta.get("section") or "Custom Articles",
            "locked": False,
            "source": "custom",
            "content": body,
            "updated_at": meta.get("updated_at") or mtime_iso,
        }

    target = _resolve_builtin_path(cleaned)
    content = target.read_text(encoding="utf-8")
    title, section = _find_builtin_meta(cleaned)
    mtime_iso = datetime.fromtimestamp(target.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "id": cleaned,
        "title": title,
        "section": section,
        "locked": True,
        "source": "builtin",
        "content": content,
        "updated_at": mtime_iso,
    }


@router.post("/api/docs/custom")
def create_custom_documentation(req: CustomDocCreateRequest) -> Dict[str, Any]:
    """Creates a new editable Markdown article under `docs/custom/`."""
    title = " ".join(req.title.splitlines()).strip()
    if not title:
        raise HTTPException(status_code=400, detail="Article title cannot be empty")
    section = " ".join(req.section.splitlines()).strip() or "Custom Articles"

    CUSTOM_DOCS_DIR.mkdir(parents=True, exist_ok=True)

    if req.slug is not None and req.slug.strip():
        slug = _validate_custom_slug(req.slug)
        target = CUSTOM_DOCS_DIR / f"{slug}.md"
        if target.exists():
            raise HTTPException(status_code=409, detail=f"Custom article '{slug}' already exists")
    else:
        base_slug = _validate_custom_slug(_slugify(title))
        slug = base_slug
        suffix = 2
        while (CUSTOM_DOCS_DIR / f"{slug}.md").exists():
            candidate = f"{base_slug[:72]}-{suffix}"
            slug = _validate_custom_slug(candidate)
            suffix += 1
        target = CUSTOM_DOCS_DIR / f"{slug}.md"

    updated_at = _utc_now_iso()
    target.write_text(
        _serialize_custom_doc(title, section, req.content, updated_at),
        encoding="utf-8",
    )
    return {
        "id": f"custom/{slug}",
        "slug": slug,
        "title": title,
        "section": section,
        "locked": False,
        "source": "custom",
        "content": req.content.lstrip("\r\n"),
        "updated_at": updated_at,
    }


@router.put("/api/docs/custom/{slug}")
def update_custom_documentation(slug: str, req: CustomDocUpdateRequest) -> Dict[str, Any]:
    """Updates an existing editable custom Markdown article in `docs/custom/`."""
    safe_slug = _validate_custom_slug(slug)
    target = CUSTOM_DOCS_DIR / f"{safe_slug}.md"
    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"Custom article '{safe_slug}' not found")

    title = " ".join(req.title.splitlines()).strip()
    if not title:
        raise HTTPException(status_code=400, detail="Article title cannot be empty")
    section = " ".join(req.section.splitlines()).strip() or "Custom Articles"

    updated_at = _utc_now_iso()
    target.write_text(
        _serialize_custom_doc(title, section, req.content, updated_at),
        encoding="utf-8",
    )
    return {
        "id": f"custom/{safe_slug}",
        "slug": safe_slug,
        "title": title,
        "section": section,
        "locked": False,
        "source": "custom",
        "content": req.content.lstrip("\r\n"),
        "updated_at": updated_at,
    }


@router.delete("/api/docs/custom/{slug}")
def delete_custom_documentation(slug: str) -> Dict[str, str]:
    """Deletes a custom Markdown article from `docs/custom/`. Built-in docs remain locked."""
    safe_slug = _validate_custom_slug(slug)
    target = CUSTOM_DOCS_DIR / f"{safe_slug}.md"
    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"Custom article '{safe_slug}' not found")
    target.unlink()
    return {"deleted": f"custom/{safe_slug}"}
