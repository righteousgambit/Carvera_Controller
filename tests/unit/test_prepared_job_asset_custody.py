"""An unchanged extraction at Apply cannot disguise different prepared geometry."""

import hashlib
from types import SimpleNamespace

import pytest

from carveracontroller.desktop_job_packages import verify_prepared_asset_custody


def test_prepared_digests_must_match_retained_archive_bytes(tmp_path):
    source = tmp_path / "cutter.json"
    source.write_bytes(b"restored original archive content")
    original = b"original archive content"
    digest = hashlib.sha256(original).hexdigest()
    loaded = SimpleNamespace(asset_paths={"asset://cutter": source}, asset_bytes={"asset://cutter": original})
    definition = SimpleNamespace(
        geometry_path=str(source), geometry_sha256=digest, holder_geometry_path=None, holder_geometry_sha256=None
    )
    prepared = (SimpleNamespace(stock_model=None), {}, None, [], None, None, None)
    verify_prepared_asset_custody(loaded, prepared, None, {1: definition})
    definition.geometry_sha256 = hashlib.sha256(b"transient changed bytes").hexdigest()
    # Disk now matches the archive again; the prepared digest still exposes the swap.
    source.write_bytes(original)
    with pytest.raises(ValueError, match="verified job archive"):
        verify_prepared_asset_custody(loaded, prepared, None, {1: definition})


@pytest.mark.parametrize("group", ["fixture", "workholding", "machine", "stock", "holder"])
def test_each_imported_geometry_identity_is_checked(tmp_path, group):
    source = tmp_path / "mesh.json"
    digest = hashlib.sha256(b"original").hexdigest()
    loaded = SimpleNamespace(asset_paths={"asset://mesh": source}, asset_bytes={"asset://mesh": b"original"})
    cad = SimpleNamespace(asset_path=str(source), asset_sha256="0" * 64)
    stock = SimpleNamespace(source_path=str(source), source_sha256="0" * 64) if group == "stock" else None
    definitions = {}
    if group == "holder":
        definitions[1] = SimpleNamespace(
            geometry_path=None, geometry_sha256=None, holder_geometry_path=str(source), holder_geometry_sha256="0" * 64
        )
    components = [(group, cad)] if group in ("fixture", "workholding") else []
    profile = {"cad_path": str(source)} if group == "machine" else None
    prepared = (SimpleNamespace(stock_model=stock), {}, profile, components, None, None, None)
    with pytest.raises(ValueError, match="verified job archive"):
        verify_prepared_asset_custody(loaded, prepared, cad if profile else None, definitions)
    cad.asset_sha256 = digest
