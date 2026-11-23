"""Tests for path_containment."""

import os
from pathlib import Path

import pytest

from path_containment import (
    UnsafePathError,
    is_within,
    safe_join,
    safe_member_name,
    safe_target,
    sanitize_filename,
)


class TestIsWithin:
    def test_the_directory_itself(self, tmp_path):
        assert is_within(tmp_path, tmp_path) is True

    def test_a_child(self, tmp_path):
        assert is_within(tmp_path, tmp_path / "a" / "b.txt") is True

    def test_a_sibling(self, tmp_path):
        assert is_within(tmp_path / "a", tmp_path / "b") is False

    def test_a_parent(self, tmp_path):
        assert is_within(tmp_path / "a", tmp_path) is False

    def test_relative_input_is_resolved(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert is_within(".", "sub/file.txt") is True

    @pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
    def test_a_symlink_pointing_outside_is_not_within(self, tmp_path):
        outside = tmp_path / "outside"
        outside.mkdir()
        base = tmp_path / "base"
        base.mkdir()
        (base / "link").symlink_to(outside)
        assert is_within(base, base / "link") is False


class TestSafeJoin:
    def test_a_simple_name(self, tmp_path):
        assert safe_join(tmp_path, "a.txt") == tmp_path.resolve() / "a.txt"

    def test_several_parts(self, tmp_path):
        assert safe_join(tmp_path, "a", "b", "c.txt") == tmp_path.resolve() / "a" / "b" / "c.txt"

    def test_no_parts(self, tmp_path):
        assert safe_join(tmp_path) == tmp_path.resolve()

    def test_empty_and_dot_parts_are_skipped(self, tmp_path):
        assert safe_join(tmp_path, "", ".", "a.txt") == tmp_path.resolve() / "a.txt"

    def test_parent_traversal_is_refused(self, tmp_path):
        with pytest.raises(UnsafePathError, match="parent directory"):
            safe_join(tmp_path, "../escape.txt")

    def test_traversal_in_the_middle_is_refused(self, tmp_path):
        with pytest.raises(UnsafePathError, match="parent directory"):
            safe_join(tmp_path, "a/../../escape.txt")

    def test_an_absolute_part_is_refused(self, tmp_path):
        with pytest.raises(UnsafePathError, match="absolute"):
            safe_join(tmp_path, "/etc/passwd")

    def test_a_windows_drive_is_refused(self, tmp_path):
        with pytest.raises(UnsafePathError, match="absolute"):
            safe_join(tmp_path, "C:\\Windows\\system32")

    def test_a_control_character_is_refused(self, tmp_path):
        with pytest.raises(UnsafePathError, match="control character"):
            safe_join(tmp_path, "a\x00b")

    def test_accepts_a_string_base(self, tmp_path):
        assert safe_join(str(tmp_path), "a.txt").name == "a.txt"

    def test_backslashes_are_treated_as_separators(self, tmp_path):
        with pytest.raises(UnsafePathError, match="parent directory"):
            safe_join(tmp_path, "..\\escape.txt")

    @pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
    def test_a_symlinked_directory_inside_cannot_escape(self, tmp_path):
        outside = tmp_path / "outside"
        outside.mkdir()
        base = tmp_path / "base"
        base.mkdir()
        (base / "link").symlink_to(outside)
        with pytest.raises(UnsafePathError, match="outside"):
            safe_join(base, "link", "a.txt")


class TestSafeMemberName:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("a.txt", "a.txt"),
            ("docs/a.txt", "docs/a.txt"),
            ("./docs/a.txt", "docs/a.txt"),
            ("docs\\a.txt", "docs/a.txt"),
            ("docs//a.txt", "docs/a.txt"),
        ],
    )
    def test_names_are_normalised(self, raw, expected):
        assert safe_member_name(raw) == expected

    @pytest.mark.parametrize("raw", ["../a.txt", "/etc/passwd", "C:\\a.txt", "docs/../../a.txt"])
    def test_escapes_are_refused(self, raw):
        with pytest.raises(UnsafePathError):
            safe_member_name(raw)

    def test_an_empty_name_is_refused(self):
        with pytest.raises(UnsafePathError, match="empty"):
            safe_member_name("   ")

    def test_a_dot_name_is_refused(self):
        with pytest.raises(UnsafePathError, match="nothing"):
            safe_member_name(".")

    def test_a_control_character_is_refused(self):
        with pytest.raises(UnsafePathError, match="control character"):
            safe_member_name("a\tb") if False else safe_member_name("a\nb")


class TestSafeTarget:
    def test_member_inside_the_directory(self, tmp_path):
        assert safe_target(tmp_path, "docs/a.txt") == tmp_path.resolve() / "docs" / "a.txt"

    def test_traversal_is_refused(self, tmp_path):
        with pytest.raises(UnsafePathError):
            safe_target(tmp_path, "../../etc/passwd")

    def test_windows_style_traversal_is_refused(self, tmp_path):
        with pytest.raises(UnsafePathError):
            safe_target(tmp_path, "..\\..\\windows\\system32")


class TestSanitizeFilename:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("report.pdf", "report.pdf"),
            ("my file.txt", "my file.txt"),
            ("a/b.txt", "a_b.txt"),
            ("a\\b.txt", "a_b.txt"),
            ("bad:name?.txt", "bad_name_.txt"),
            ("keep-this_ok.txt", "keep-this_ok.txt"),
            ("ünïcode.txt", "ünïcode.txt"),
        ],
    )
    def test_characters_are_replaced(self, raw, expected):
        assert sanitize_filename(raw) == expected

    def test_trailing_dots_and_spaces_are_removed(self):
        assert sanitize_filename("name.txt.  ") == "name.txt"

    def test_control_characters_are_replaced(self):
        assert sanitize_filename("a\nb\x00c.txt") == "a_b_c.txt"

    @pytest.mark.parametrize("reserved", ["CON", "nul", "COM1", "lpt9"])
    def test_reserved_device_names_are_prefixed(self, reserved):
        assert sanitize_filename(reserved).startswith("_")

    def test_reserved_name_check_ignores_the_extension(self):
        assert sanitize_filename("con.txt") == "_con.txt"

    def test_a_reserved_looking_name_is_fine(self):
        assert sanitize_filename("console.txt") == "console.txt"

    def test_a_custom_replacement(self):
        assert sanitize_filename("a/b", replacement="-") == "a-b"

    def test_empty_input_falls_back_to_the_replacement(self):
        assert sanitize_filename("") == "_"
        assert sanitize_filename("...", replacement="x") == "x"

    def test_length_is_capped(self):
        assert len(sanitize_filename("a" * 400, max_length=32)) == 32

    def test_the_cap_does_not_leave_a_trailing_dot(self):
        assert sanitize_filename("a" * 30 + ".txt", max_length=31).endswith("a")

    def test_a_bad_max_length_raises(self):
        with pytest.raises(ValueError, match="max_length"):
            sanitize_filename("a", max_length=0)


class TestRigour:
    """A resolved path outside the root is refused, whatever produced it."""

    def test_a_symlinked_directory_that_escapes_is_refused(self, tmp_path, monkeypatch):
        root = tmp_path / "root"
        root.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()

        real_resolve = Path.resolve

        def fake(self, *args, **kwargs):
            if self.name == "escape":
                return outside
            return real_resolve(self, *args, **kwargs)

        monkeypatch.setattr(Path, "resolve", fake)
        with pytest.raises(UnsafePathError, match="outside"):
            safe_join(root, "escape")

    def test_the_root_itself_is_allowed(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        assert safe_join(root) == root.resolve()

    def test_an_empty_or_dot_part_is_skipped(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        assert safe_join(root, "", ".", "a.txt") == (root / "a.txt").resolve()
