"""Tests for inspire.cli.utils.id_resolver."""

from __future__ import annotations

from unittest.mock import patch

import click
import pytest

from inspire.cli.utils.id_resolver import (
    is_full_uuid,
    is_partial_id,
    normalize_partial,
    resolve_partial_id,
    resolve_by_name,
)


# ---------------------------------------------------------------------------
# is_full_uuid
# ---------------------------------------------------------------------------


class TestIsFullUuid:
    def test_standard_uuid(self):
        assert is_full_uuid("c4eb3ac3-6d83-405c-aa29-059bc945c4bf") is True

    def test_uppercase_uuid(self):
        assert is_full_uuid("C4EB3AC3-6D83-405C-AA29-059BC945C4BF") is True

    def test_with_prefix(self):
        assert is_full_uuid("job-c4eb3ac3-6d83-405c-aa29-059bc945c4bf", prefix="job-") is True

    def test_prefix_case_insensitive(self):
        assert is_full_uuid("JOB-c4eb3ac3-6d83-405c-aa29-059bc945c4bf", prefix="job-") is True

    def test_uuid_without_matching_prefix(self):
        # "job-" prefix present but we strip "notebook-" — leaves "job-..." which is not a UUID
        assert is_full_uuid("job-c4eb3ac3-6d83-405c-aa29-059bc945c4bf", prefix="notebook-") is False

    def test_partial_hex_not_full(self):
        assert is_full_uuid("c4eb3ac3") is False

    def test_empty(self):
        assert is_full_uuid("") is False

    def test_whitespace_stripped(self):
        assert is_full_uuid("  c4eb3ac3-6d83-405c-aa29-059bc945c4bf  ") is True


# ---------------------------------------------------------------------------
# is_partial_id
# ---------------------------------------------------------------------------


class TestIsPartialId:
    def test_four_hex_chars(self):
        assert is_partial_id("abcd") is True

    def test_eight_hex_chars(self):
        assert is_partial_id("c4eb3ac3") is True

    def test_too_short(self):
        assert is_partial_id("abc") is False

    def test_full_uuid_not_partial(self):
        assert is_partial_id("c4eb3ac3-6d83-405c-aa29-059bc945c4bf") is False

    def test_non_hex(self):
        assert is_partial_id("mynotebook") is False

    def test_with_prefix(self):
        assert is_partial_id("job-c4eb3ac3", prefix="job-") is True

    def test_prefix_stripped_too_short(self):
        assert is_partial_id("job-ab", prefix="job-") is False

    def test_mixed_case_hex(self):
        assert is_partial_id("AbCd1234") is True

    def test_empty(self):
        assert is_partial_id("") is False

    def test_hex_with_hyphens_no_prefix(self):
        # "abcd-1234" is not pure hex (has hyphens), but not a full UUID
        assert is_partial_id("abcd-1234") is False

    def test_long_hex_not_uuid_format(self):
        # 32 hex chars without hyphens — partial, not a full UUID
        assert is_partial_id("c4eb3ac36d83405caa29059bc945c4bf") is True


# ---------------------------------------------------------------------------
# normalize_partial
# ---------------------------------------------------------------------------


class TestNormalizePartial:
    def test_lowercase(self):
        assert normalize_partial("ABCD1234") == "abcd1234"

    def test_strip_prefix(self):
        assert normalize_partial("job-c4eb3ac3", prefix="job-") == "c4eb3ac3"

    def test_prefix_case_insensitive(self):
        assert normalize_partial("JOB-C4EB3AC3", prefix="job-") == "c4eb3ac3"

    def test_no_prefix(self):
        assert normalize_partial("c4eb3ac3") == "c4eb3ac3"

    def test_whitespace(self):
        assert normalize_partial("  ABCD  ") == "abcd"


# ---------------------------------------------------------------------------
# resolve_partial_id
# ---------------------------------------------------------------------------


class _FakeContext:
    """Minimal stand-in for Context."""

    def __init__(self, json_output: bool = False):
        self.json_output = json_output


class TestResolvePartialId:
    def test_single_match(self):
        ctx = _FakeContext()
        result = resolve_partial_id(
            ctx,
            "c4eb",
            "job",
            [("job-c4eb3ac3-6d83-405c-aa29-059bc945c4bf", "my-job")],
            json_output=False,
        )
        assert result == "job-c4eb3ac3-6d83-405c-aa29-059bc945c4bf"

    def test_no_matches_exits(self):
        ctx = _FakeContext()
        with pytest.raises(SystemExit):
            resolve_partial_id(ctx, "zzzz", "job", [], json_output=False)

    def test_multiple_matches_json_exits(self):
        ctx = _FakeContext(json_output=True)
        matches = [
            ("job-aaaa1111-0000-0000-0000-000000000001", "job-a"),
            ("job-aaaa2222-0000-0000-0000-000000000002", "job-b"),
        ]
        with pytest.raises(SystemExit):
            resolve_partial_id(ctx, "aaaa", "job", matches, json_output=True)

    def test_multiple_matches_interactive_prompts(self):
        ctx = _FakeContext()
        matches = [
            ("job-aaaa1111-0000-0000-0000-000000000001", "job-a"),
            ("job-aaaa2222-0000-0000-0000-000000000002", "job-b"),
        ]
        with patch.object(click, "prompt", return_value=2):
            result = resolve_partial_id(ctx, "aaaa", "job", matches, json_output=False)
        assert result == "job-aaaa2222-0000-0000-0000-000000000002"

    def test_interactive_default_first(self):
        ctx = _FakeContext()
        matches = [
            ("id-1", "first"),
            ("id-2", "second"),
        ]
        with patch.object(click, "prompt", return_value=1):
            result = resolve_partial_id(ctx, "id", "resource", matches, json_output=False)
        assert result == "id-1"


class TestResolveByName:
    def test_handle_shaped_error_omits_id_hint_by_default(self, capsys):
        ctx = _FakeContext(json_output=True)

        with pytest.raises(SystemExit):
            resolve_by_name(
                ctx,
                name="image-c4eb3ac3-6d83-405c-aa29-059bc945c4bf",
                resource_type="image",
                list_candidates=lambda: [],
                json_output=True,
            )

        captured = capsys.readouterr()
        assert "inspire image list" in captured.err
        assert "dedicated `id` command" not in captured.err

    def test_handle_shaped_error_uses_custom_id_hint(self, capsys):
        ctx = _FakeContext(json_output=True)

        with pytest.raises(SystemExit):
            resolve_by_name(
                ctx,
                name="hpc-job-c4eb3ac3-6d83-405c-aa29-059bc945c4bf",
                resource_type="hpc",
                list_candidates=lambda: [],
                json_output=True,
                id_lookup_hint="Use `inspire hpc id <name>` for explicit platform-handle lookup.",
            )

        assert "inspire hpc id <name>" in capsys.readouterr().err

    def test_date_suffixed_names_are_not_treated_as_handles(self):
        ctx = _FakeContext(json_output=True)

        result = resolve_by_name(
            ctx,
            name="job-smoke-20260507",
            resource_type="job",
            list_candidates=lambda: [{"name": "job-smoke-20260507", "id": "job-id"}],
            json_output=True,
        )

        assert result == "job-id"

    @pytest.mark.parametrize(
        "name, resource_type",
        [
            ("hpc-job-123", "hpc"),
            ("rj-abc", "ray"),
            ("ray-abc-1", "ray"),
            ("img-001", "image"),
            ("image-abc-def", "image"),
        ],
    )
    def test_compact_platform_handles_are_rejected_before_listing(
        self,
        name: str,
        resource_type: str,
        capsys,
    ):
        ctx = _FakeContext(json_output=True)

        def _fail_lister():
            raise AssertionError("compact handle should be rejected before listing")

        with pytest.raises(SystemExit):
            resolve_by_name(
                ctx,
                name=name,
                resource_type=resource_type,
                list_candidates=_fail_lister,
                json_output=True,
            )

        assert f"{resource_type} name" in capsys.readouterr().err
