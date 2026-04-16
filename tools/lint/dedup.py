"""Duplicate detection and merging."""

import json
import re
from pathlib import Path

import frontmatter

from ..config import load_config, ensure_dirs
from ..llm import chat


def _find_duplicate_candidates(articles: list[dict]) -> list[tuple[str, str]]:
    """Pre-filter: find article pairs that are likely duplicates.

    Uses cheap heuristics — no LLM call:
    - Slug substring overlap (ASCII: min 4 chars; CJK: any length)
    - High tag overlap (>= 60% Jaccard)
    - CJK substring matching across titles AND slugs
      (仁 is substring of 仁爱 → candidate)
    """
    import re
    cjk_re = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf]')

    candidates = []
    n = len(articles)

    def _is_cjk(text: str) -> bool:
        return bool(cjk_re.search(text))

    def _extract_cjk(text: str) -> str:
        """Extract all CJK characters from text."""
        return re.sub(r'[^\u4e00-\u9fff\u3400-\u4dbf]', '', text)

    def _all_cjk_names(article: dict) -> set[str]:
        """Get all CJK names for an article: from title parts AND slug."""
        names = set()
        # From title: split by / and extract CJK
        for part in article["title"].split("/"):
            cjk = _extract_cjk(part.strip())
            if cjk:
                names.add(cjk)
        # From slug if it contains CJK
        slug_cjk = _extract_cjk(article["slug"])
        if slug_cjk:
            names.add(slug_cjk)
        return names

    def _simplify(text: str) -> str:
        """Convert traditional Chinese to simplified for comparison."""
        try:
            from opencc import OpenCC
            return OpenCC('t2s').convert(text)
        except ImportError:
            return text

    def _cjk_substring_match(names_a: set[str], names_b: set[str]) -> bool:
        """Check if CJK names match (exact, simplified/traditional, or near-exact).

        Rules:
        - Exact match (including after simplification): always match
        - Single char (仁): exact only, no substring
        - 2+ chars: substring OK if >= 67% of longer string
        """
        # Expand both sets with simplified variants
        expanded_a = names_a | {_simplify(n) for n in names_a}
        expanded_b = names_b | {_simplify(n) for n in names_b}

        for a in expanded_a:
            for b in expanded_b:
                if a == b:
                    return True
                short, long = (a, b) if len(a) <= len(b) else (b, a)
                if len(short) <= 1:
                    continue
                if short in long and len(short) / len(long) >= 0.67:
                    return True
        return False

    for i in range(n):
        for j in range(i + 1, n):
            a, b = articles[i], articles[j]
            score = 0

            # Slug substring matching
            a_slug, b_slug = a["slug"], b["slug"]
            if _is_cjk(a_slug) or _is_cjk(b_slug):
                # CJK slug: no minimum length
                if a_slug in b_slug or b_slug in a_slug:
                    score += 2
            else:
                # ASCII slug: min 4 chars to avoid "ren" in "renzhe" false positive
                if len(a_slug) >= 4 and a_slug in b_slug:
                    score += 2
                elif len(b_slug) >= 4 and b_slug in a_slug:
                    score += 2

            # Tag Jaccard similarity
            if a["tags"] and b["tags"]:
                intersection = len(a["tags"] & b["tags"])
                union = len(a["tags"] | b["tags"])
                if union > 0 and intersection / union >= 0.6:
                    score += 2

            # CJK name substring matching (the key fix)
            # Collects CJK from title parts AND slug, then does substring comparison
            cjk_a = _all_cjk_names(a)
            cjk_b = _all_cjk_names(b)
            if cjk_a and cjk_b and _cjk_substring_match(cjk_a, cjk_b):
                score += 3

            if score >= 2:
                candidates.append((a["slug"], b["slug"]))

    return candidates



def merge_duplicates(base_dir: Path | None = None, max_merges: int = 15) -> list[str]:
    """Merge confirmed duplicate articles using LLM.

    For each duplicate pair:
    1. LLM picks the primary article (better slug/title)
    2. Content from secondary is appended to primary (叠加进化)
    3. Secondary is deleted, all [[wiki-links]] pointing to it are rewritten
    4. Index and backlinks are rebuilt
    """
    cfg = load_config(base_dir)
    ensure_dirs(cfg)
    concepts_dir = Path(cfg["paths"]["concepts"])

    from .checks import check_duplicates
    duplicates = check_duplicates(cfg)
    confirmed = [d for d in duplicates if d.startswith("Likely duplicate:")]

    if not confirmed:
        return []

    fixes = []
    for issue in confirmed[:max_merges]:
        # Parse "Likely duplicate: slug-a <-> slug-b"
        parts = issue.replace("Likely duplicate: ", "").split(" <-> ")
        if len(parts) != 2:
            continue
        slug_a, slug_b = parts[0].strip(), parts[1].strip()
        path_a = concepts_dir / f"{slug_a}.md"
        path_b = concepts_dir / f"{slug_b}.md"

        if not path_a.exists() or not path_b.exists():
            continue

        post_a = frontmatter.load(str(path_a))
        post_b = frontmatter.load(str(path_b))

        # Pick primary — rule-based, no LLM needed:
        # ASCII slug preferred over CJK slug; longer content wins
        import re as _re
        a_is_ascii = not bool(_re.search(r'[\u4e00-\u9fff]', slug_a))
        b_is_ascii = not bool(_re.search(r'[\u4e00-\u9fff]', slug_b))

        if a_is_ascii and not b_is_ascii:
            choose_b = False
        elif b_is_ascii and not a_is_ascii:
            choose_b = True
        else:
            choose_b = len(post_b.content) > len(post_a.content)

        if choose_b:
            primary_path, secondary_path = path_b, path_a
            primary_slug, secondary_slug = slug_b, slug_a
        else:
            primary_path, secondary_path = path_a, path_b
            primary_slug, secondary_slug = slug_a, slug_b

        primary = frontmatter.load(str(primary_path))
        secondary = frontmatter.load(str(secondary_path))

        # Merge content (叠加进化)
        if secondary.content.strip() and secondary.content.strip() not in primary.content:
            primary.content += f"\n\n---\n*Merged from [[{secondary_slug}]]:*\n\n{secondary.content}"

        # Merge tags
        old_tags = set(primary.metadata.get("tags", []))
        new_tags = set(secondary.metadata.get("tags", []))
        primary.metadata["tags"] = sorted(old_tags | new_tags)

        from datetime import datetime, timezone
        primary.metadata["updated"] = datetime.now(timezone.utc).isoformat()
        primary.metadata["merged_from"] = primary.metadata.get("merged_from", [])
        primary.metadata["merged_from"].append(secondary_slug)

        primary_path.write_text(frontmatter.dumps(primary), encoding="utf-8")

        # Rewrite all [[secondary_slug]] links to [[primary_slug]]
        _rewrite_links(concepts_dir, secondary_slug, primary_slug)

        # Delete secondary
        secondary_path.unlink()
        fixes.append(f"Merged {secondary_slug} → {primary_slug}")

    # Rebuild index + update taxonomy if any merges happened
    if fixes:
        from ..compile import rebuild_index
        rebuild_index(base_dir)
        _refresh_taxonomy_after_merge(base_dir)

    return fixes



def _refresh_taxonomy_after_merge(base_dir: Path | None = None):
    """Update taxonomy.json to reflect merged articles.

    Removes deleted slugs and adds any new slugs not yet in the tree.
    Preserves the locked flag and category structure.
    """
    import json
    cfg = load_config(base_dir)
    meta_dir = Path(cfg["paths"]["meta"])
    concepts_dir = Path(cfg["paths"]["concepts"])
    tax_path = meta_dir / "taxonomy.json"

    if not tax_path.exists():
        return

    taxonomy = json.loads(tax_path.read_text())
    existing_slugs = {f.stem for f in concepts_dir.glob("*.md")}

    # Collect all slugs currently in taxonomy
    def _collect_slugs(nodes):
        all_s = set()
        for n in nodes:
            all_s.update(n.get("article_slugs", []))
            all_s.update(_collect_slugs(n.get("children", [])))
        return all_s

    def _remove_dead_slugs(nodes):
        for n in nodes:
            n["article_slugs"] = [s for s in n.get("article_slugs", []) if s in existing_slugs]
            _remove_dead_slugs(n.get("children", []))

    categories = taxonomy.get("categories", [])
    _remove_dead_slugs(categories)

    # Find slugs not in any category
    assigned = _collect_slugs(categories)
    unassigned = existing_slugs - assigned
    if unassigned:
        # Add to "Other" category
        other = None
        for c in categories:
            if c.get("id") in ("other", "其他"):
                other = c
                break
        if other:
            other["article_slugs"] = list(set(other.get("article_slugs", [])) | unassigned)
        else:
            categories.append({
                "id": "other",
                "label": {"en": "Other", "zh": "其他", "ja": "その他"},
                "article_slugs": list(unassigned),
                "children": [],
            })

    taxonomy["categories"] = categories
    tax_path.write_text(json.dumps(taxonomy, indent=2, ensure_ascii=False), encoding="utf-8")



def _rewrite_links(concepts_dir: Path, old_slug: str, new_slug: str):
    """Rewrite all [[old_slug]] references to [[new_slug]] across the wiki."""
    for md_file in concepts_dir.glob("*.md"):
        content = md_file.read_text()
        # Match [[old_slug]] and [[old_slug|display text]]
        new_content = re.sub(
            rf"\[\[{re.escape(old_slug)}(\|[^\]]+)?\]\]",
            lambda m: f"[[{new_slug}{m.group(1) or ''}]]",
            content,
        )
        if new_content != content:
            md_file.write_text(new_content, encoding="utf-8")


