# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import os
import errno
import pathlib
from unittest.mock import ANY
from string import ascii_lowercase
from contextlib import contextmanager

import attr
import pytest
from pendulum import Pendulum
from hypothesis_trio.stateful import (
    TrioRuleBasedStateMachine,
    initialize,
    invariant,
    rule,
    run_state_machine_as_test,
    Bundle,
)
from hypothesis import strategies as st

from parsec.core.types import FsPath
from parsec.core.backend_connection import BackendCmdsNotFound
from parsec.core.fs.utils import is_folder_manifest

from tests.common import freeze_time


@pytest.mark.trio
async def test_root_entry_info(entry_transactions):
    stat = await entry_transactions.entry_info(FsPath("/"))
    assert stat == {
        "type": "folder",
        "id": entry_transactions.workspace_entry.access.id,
        "base_version": 0,
        "is_placeholder": True,
        "need_sync": True,
        "created": Pendulum(2000, 1, 1),
        "updated": Pendulum(2000, 1, 1),
        "children": [],
    }


@pytest.mark.trio
async def test_file_create(file_transactions, entry_transactions, alice):

    with freeze_time("2000-01-02"):
        access_id, fd = await entry_transactions.file_create(FsPath("/foo.txt"))
        await file_transactions.fd_close(fd)

    assert fd == 1
    root_stat = await entry_transactions.entry_info(FsPath("/"))
    assert root_stat == {
        "type": "folder",
        "id": ANY,
        "base_version": 0,
        "is_placeholder": True,
        "need_sync": True,
        "created": Pendulum(2000, 1, 1),
        "updated": Pendulum(2000, 1, 2),
        "children": ["foo.txt"],
    }

    foo_stat = await entry_transactions.entry_info(FsPath("/foo.txt"))
    assert foo_stat == {
        "type": "file",
        "id": ANY,
        "base_version": 0,
        "is_placeholder": True,
        "need_sync": True,
        "created": Pendulum(2000, 1, 2),
        "updated": Pendulum(2000, 1, 2),
        "size": 0,
    }


@pytest.mark.trio
async def test_rename_non_empty_folder(entry_transactions, file_transactions):
    with freeze_time("2000-01-02"):
        await entry_transactions.folder_create(FsPath("/foo"))
        await entry_transactions.folder_create(FsPath("/foo/bar"))
        await entry_transactions.folder_create(FsPath("/foo/bar/zob"))
        fd = await entry_transactions.file_create(FsPath("/foo/bar/zob/fizz.txt"))
        await file_transactions.fd_close(fd)
        fd = await entry_transactions.file_create(FsPath("/foo/spam.txt"))
        await file_transactions.fd_close(fd)

    await entry_transactions.entry_rename(FsPath("/foo"), FsPath("/foo2"))
    stat = await entry_transactions.entry_info(FsPath("/"))
    assert stat["children"] == ["foo2"]

    await entry_transactions.entry_info(FsPath("/foo2"))
    await entry_transactions.entry_info(FsPath("/foo2/bar"))
    await entry_transactions.entry_info(FsPath("/foo2/bar/zob"))
    await entry_transactions.entry_info(FsPath("/foo2/bar/zob/fizz.txt"))
    await entry_transactions.entry_info(FsPath("/foo2/spam.txt"))


@pytest.mark.trio
async def test_cannot_replace_root(entry_transactions):
    with pytest.raises(PermissionError):
        await entry_transactions.file_create(FsPath("/"), open=False)
    with pytest.raises(PermissionError):
        await entry_transactions.folder_create(FsPath("/"))

    with pytest.raises(PermissionError):
        await entry_transactions.entry_rename(FsPath("/"), FsPath("/foo"))

    await entry_transactions.folder_create(FsPath("/foo"))
    with pytest.raises(PermissionError):
        await entry_transactions.entry_rename(FsPath("/foo"), FsPath("/"))


@pytest.mark.trio
async def test_access_not_loaded_entry(alice, bob, entry_transactions):

    access = entry_transactions.workspace_entry.access
    manifest = entry_transactions.local_storage.get_manifest(access)
    entry_transactions.local_storage.clear_manifest(access)

    with pytest.raises(BackendCmdsNotFound):
        await entry_transactions.entry_info(FsPath("/"))

    entry_transactions.local_storage.set_dirty_manifest(access, manifest)
    entry_info = await entry_transactions.entry_info(FsPath("/"))
    assert entry_info == {
        "type": "folder",
        "id": access.id,
        "created": Pendulum(2000, 1, 1),
        "updated": Pendulum(2000, 1, 1),
        "base_version": 0,
        "is_placeholder": True,
        "need_sync": True,
        "children": [],
    }


@pytest.mark.trio
async def test_access_unknown_entry(entry_transactions):
    with pytest.raises(FileNotFoundError):
        await entry_transactions.entry_info(FsPath("/dummy"))


@contextmanager
def expect_raises(expected, *args, **kwargs):
    if expected is None:
        yield
        return
    with pytest.raises(type(expected), *args, **kwargs):
        yield


def oracle_rename(src, dst):
    """The oracle must behave differently than `src.rename`, as the
    workspace file system does not support cross-directory renaming.
    """
    if src.parent != dst.parent:
        raise OSError(errno.EXDEV, os.strerror(errno.EXDEV))
    return src.rename(str(dst))


@attr.s
class PathElement:
    absolute_path = attr.ib()
    oracle_root = attr.ib()

    def to_oracle(self):
        return self.oracle_root / self.absolute_path[1:]

    def to_parsec(self):
        return FsPath(self.absolute_path)

    def __truediv__(self, path):
        return PathElement(os.path.join(self.absolute_path, path), self.oracle_root)


@pytest.mark.slow
@pytest.mark.skipif(os.name == "nt", reason="Windows path style not compatible with oracle")
def test_folder_operations(
    tmpdir,
    hypothesis_settings,
    local_storage_factory,
    entry_transactions_factory,
    file_transactions_factory,
    alice,
    alice_backend_cmds,
):
    tentative = 0

    # The point is not to find breaking filenames here, so keep it simple
    st_entry_name = st.text(alphabet=ascii_lowercase, min_size=1, max_size=3)

    class FileOperationsStateMachine(TrioRuleBasedStateMachine):
        Files = Bundle("file")
        Folders = Bundle("folder")

        @initialize(target=Folders)
        async def init_root(self):
            nonlocal tentative
            tentative += 1

            self.last_step_id_to_path = set()
            self.device = alice
            self.local_storage = local_storage_factory(self.device)
            self.entry_transactions = entry_transactions_factory(
                self.device, self.local_storage, alice_backend_cmds
            )
            self.file_transactions = file_transactions_factory(
                self.device, self.local_storage, alice_backend_cmds
            )

            self.folder_oracle = pathlib.Path(tmpdir / f"oracle-test-{tentative}")
            self.folder_oracle.mkdir()
            oracle_root = self.folder_oracle / "root"
            oracle_root.mkdir()
            self.folder_oracle.chmod(0o500)  # Root oracle can no longer be removed this way
            return PathElement("/", oracle_root)

        @rule(target=Files, parent=Folders, name=st_entry_name)
        async def touch(self, parent, name):
            path = parent / name

            expected_exc = None
            try:
                path.to_oracle().touch(exist_ok=False)
            except OSError as exc:
                expected_exc = exc

            with expect_raises(expected_exc):
                fd = await self.entry_transactions.file_create(path.to_parsec())
                await self.file_transactions.fd_close(fd)
            return path

        @rule(target=Folders, parent=Folders, name=st_entry_name)
        async def mkdir(self, parent, name):
            path = parent / name

            expected_exc = None
            try:
                path.to_oracle().mkdir(exist_ok=False)
            except OSError as exc:
                expected_exc = exc

            with expect_raises(expected_exc):
                await self.entry_transactions.folder_create(path.to_parsec())

            return path

        @rule(path=Files)
        async def unlink(self, path):
            expected_exc = None
            try:
                path.to_oracle().unlink()
            except OSError as exc:
                expected_exc = exc

            with expect_raises(expected_exc):
                await self.entry_transactions.file_delete(path.to_parsec())

        @rule(path=Folders)
        async def rmdir(self, path):
            expected_exc = None
            try:
                path.to_oracle().rmdir()
            except OSError as exc:
                expected_exc = exc

            with expect_raises(expected_exc):
                await self.entry_transactions.folder_delete(path.to_parsec())

        async def _rename(self, src, dst_parent, dst_name):
            dst = dst_parent / dst_name

            expected_exc = None
            try:
                oracle_rename(src.to_oracle(), dst.to_oracle())
            except OSError as exc:
                expected_exc = exc

            with expect_raises(expected_exc):
                await self.entry_transactions.entry_rename(src.to_parsec(), dst.to_parsec())

            return dst

        @rule(target=Files, src=Files, dst_parent=Folders, dst_name=st_entry_name)
        async def rename_file(self, src, dst_parent, dst_name):
            return await self._rename(src, dst_parent, dst_name)

        @rule(target=Folders, src=Folders, dst_parent=Folders, dst_name=st_entry_name)
        async def rename_folder(self, src, dst_parent, dst_name):
            return await self._rename(src, dst_parent, dst_name)

        @invariant()
        async def check_access_to_path_unicity(self):
            try:
                self.entry_transactions
            except AttributeError:
                return

            local_storage = self.entry_transactions.local_storage
            root_access = self.entry_transactions.workspace_entry.access
            new_id_to_path = set()

            def _recursive_build_id_to_path(access, path):
                new_id_to_path.add((access.id, path))
                manifest = local_storage.get_manifest(access)
                if is_folder_manifest(manifest):
                    for child_name, child_access in manifest.children.items():
                        _recursive_build_id_to_path(child_access, path / "child_name")

            _recursive_build_id_to_path(root_access, FsPath("/"))

            added_items = new_id_to_path - self.last_step_id_to_path
            for added_id, added_path in added_items:
                for old_id, old_path in self.last_step_id_to_path:
                    if old_id == added_id and added_path.parent != old_path.parent:
                        raise AssertionError(
                            f"Same id ({old_id}) but different path: {old_path} -> {added_path}"
                        )

            self.last_step_id_to_path = new_id_to_path

    run_state_machine_as_test(FileOperationsStateMachine, settings=hypothesis_settings)
