from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path, PurePosixPath

from scripts import hermes_install_probe


class FakeDistribution:
    def __init__(
        self,
        *,
        files: list[PurePosixPath] | None = None,
        direct_url: dict[str, object] | None = None,
        root: Path | None = None,
    ) -> None:
        self.files = files
        self._direct_url = direct_url
        self._root = root

    def read_text(self, name: str) -> str | None:
        if name != "direct_url.json" or self._direct_url is None:
            return None
        return json.dumps(self._direct_url)

    def locate_file(self, item: PurePosixPath) -> Path:
        assert self._root is not None
        return self._root / item.as_posix()


class HermesInstallProbeTests(unittest.TestCase):
    def test_resolves_editable_source_from_direct_url(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module = root / "hermes_cli" / "main.py"
            module.parent.mkdir()
            module.write_text("", encoding="utf-8")
            distribution = FakeDistribution(
                files=[],
                direct_url={"url": root.as_uri(), "dir_info": {"editable": True}},
            )
            resolved, mode, source_root = hermes_install_probe._resolve_module_file(
                distribution  # type: ignore[arg-type]
            )
        self.assertEqual(resolved, module.resolve())
        self.assertEqual(mode, "editable")
        self.assertEqual(source_root, root.resolve())

    def test_rejects_non_file_editable_url(self) -> None:
        distribution = FakeDistribution(
            files=[],
            direct_url={
                "url": "https://example.invalid/hermes-agent",
                "dir_info": {"editable": True},
            },
        )
        self.assertIsNone(
            hermes_install_probe._editable_source_root(  # type: ignore[arg-type]
                distribution
            )
        )

    def test_prefers_packaged_module_when_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module = root / "hermes_cli" / "main.py"
            module.parent.mkdir()
            module.write_text("", encoding="utf-8")
            distribution = FakeDistribution(
                files=[PurePosixPath("hermes_cli/main.py")],
                root=root,
            )
            resolved, mode, source_root = hermes_install_probe._resolve_module_file(
                distribution  # type: ignore[arg-type]
            )
        self.assertEqual(resolved, module.resolve())
        self.assertEqual(mode, "installed-files")
        self.assertIsNone(source_root)


if __name__ == "__main__":
    unittest.main()
