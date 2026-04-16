"""Lint package — health checks, auto-fix, and deduplication.

Re-exports all public functions for backward compatibility:
    from tools.lint import lint, auto_fix, check_broken_links, ...
"""

from .checks import (
    lint,
    lint_deep,
    check_structural,
    check_broken_links,
    check_orphans,
    check_missing_metadata,
    check_dirty_tags,
    check_stubs,
    check_uncategorized,
    check_duplicates,
)

from .fixes import (
    auto_fix,
    normalize_tags,
    fix_dirty_tags,
    clean_garbage,
    fix_uncategorized,
    fix_broken_links,
)

from .dedup import (
    merge_duplicates,
    _find_duplicate_candidates,
)

__all__ = [
    "lint", "lint_deep", "auto_fix",
    "check_structural", "check_broken_links", "check_orphans",
    "check_missing_metadata", "check_dirty_tags", "check_stubs",
    "check_uncategorized", "check_duplicates",
    "normalize_tags", "fix_dirty_tags", "clean_garbage",
    "fix_uncategorized", "fix_broken_links",
    "merge_duplicates", "_find_duplicate_candidates",
]
