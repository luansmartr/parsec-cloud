# Parsec Cloud (https://parsec.cloud) Copyright (c) BUSL-1.1 2016-present Scille SAS

from typing import Optional

from .addr import BackendOrganizationAddr
from .common import (
    DateTime,
    DeviceID,
    DeviceLabel,
    EntryName,
    Enum,
    EnumItemUnit,
    ErrorVariant,
    Handle,
    HumanHandle,
    OrganizationID,
    Password,
    Path,
    Result,
    Structure,
    UserID,
    UserProfile,
    Variant,
    VlobID,
)
from .config import ClientConfig
from .events import OnClientEventCallback


class RealmRole(Enum):
    Owner = EnumItemUnit
    Manager = EnumItemUnit
    Contributor = EnumItemUnit
    Reader = EnumItemUnit


class DeviceAccessStrategy(Variant):
    class Password:
        password: Password
        key_file: Path

    class Smartcard:
        key_file: Path


class ClientStartError(ErrorVariant):
    class LoadDeviceInvalidPath:
        pass

    class LoadDeviceInvalidData:
        pass

    class LoadDeviceDecryptionFailed:
        pass

    class Internal:
        pass


async def client_start(
    config: ClientConfig, on_event_callback: OnClientEventCallback, access: DeviceAccessStrategy
) -> Result[Handle, ClientStartError]:
    raise NotImplementedError


class ClientStopError(ErrorVariant):
    class Internal:
        pass


async def client_stop(client: Handle) -> Result[None, ClientStopError]:
    raise NotImplementedError


class ClientInfoError(ErrorVariant):
    class Internal:
        pass


class ClientInfo(Structure):
    organization_addr: BackendOrganizationAddr
    organization_id: OrganizationID
    device_id: DeviceID
    user_id: UserID
    device_label: Optional[DeviceLabel]
    human_handle: Optional[HumanHandle]
    current_profile: UserProfile


async def client_info(
    client: Handle,
) -> Result[ClientInfo, ClientInfoError]:
    raise NotImplementedError


class UserInfo(Structure):
    id: UserID
    human_handle: Optional[HumanHandle]
    current_profile: UserProfile
    created_on: DateTime
    created_by: Optional[DeviceID]
    revoked_on: Optional[DateTime]
    revoked_by: Optional[DeviceID]


class DeviceInfo(Structure):
    id: DeviceID
    device_label: Optional[DeviceLabel]
    created_on: DateTime
    created_by: Optional[DeviceID]


class ClientListUsersError(ErrorVariant):
    class Internal:
        pass


async def client_list_users(
    client: Handle,
    skip_revoked: bool,
    # offset: Optional[int],
    # limit: Optional[int],
) -> Result[list[UserInfo], ClientListUsersError]:
    raise NotImplementedError


class ClientListUserDevicesError(ErrorVariant):
    class Internal:
        pass


async def client_list_user_devices(
    client: Handle,
    user: UserID,
) -> Result[list[DeviceInfo], ClientListUserDevicesError]:
    raise NotImplementedError


class ClientGetUserDeviceError(ErrorVariant):
    class NonExisting:
        pass

    class Internal:
        pass


async def client_get_user_device(
    client: Handle,
    device: DeviceID,
) -> Result[tuple[UserInfo, DeviceInfo], ClientGetUserDeviceError]:
    raise NotImplementedError


class WorkspaceUserAccessInfo(Structure):
    user_id: UserID
    human_handle: Optional[HumanHandle]
    role: RealmRole


class ClientListWorkspaceUsersError(ErrorVariant):
    class Internal:
        pass


async def client_list_workspace_users(
    client: Handle,
    realm_id: VlobID,
) -> Result[list[WorkspaceUserAccessInfo], ClientListWorkspaceUsersError]:
    raise NotImplementedError


class ClientListWorkspacesError(ErrorVariant):
    class Internal:
        pass


class WorkspaceInfo(Structure):
    id: VlobID
    name: EntryName
    self_role: RealmRole


async def client_list_workspaces(
    client: Handle,
) -> Result[list[WorkspaceInfo], ClientListWorkspacesError]:
    raise NotImplementedError


class ClientCreateWorkspaceError(ErrorVariant):
    class Internal:
        pass


async def client_create_workspace(
    client: Handle,
    name: EntryName,
) -> Result[VlobID, ClientCreateWorkspaceError]:
    raise NotImplementedError


class ClientRenameWorkspaceError(ErrorVariant):
    class UnknownWorkspace:
        pass

    class Internal:
        pass


async def client_rename_workspace(
    client: Handle,
    realm_id: VlobID,
    new_name: EntryName,
) -> Result[None, ClientRenameWorkspaceError]:
    raise NotImplementedError


class ClientShareWorkspaceError(ErrorVariant):
    class ShareToSelf:
        pass

    class UnknownWorkspace:
        pass

    class UnknownRecipient:
        pass

    class UnknownRecipientOrWorkspace:
        pass

    class RevokedRecipient:
        pass

    class WorkspaceInMaintenance:
        pass

    class NotAllowed:
        pass

    class OutsiderCannotBeManagerOrOwner:
        pass

    class Offline:
        pass

    class BadTimestamp:
        server_timestamp: DateTime
        client_timestamp: DateTime
        ballpark_client_early_offset: float
        ballpark_client_late_offset: float

    class Internal:
        pass


async def client_share_workspace(
    client: Handle,
    realm_id: VlobID,
    recipient: UserID,
    role: Optional[RealmRole],
) -> Result[None, ClientShareWorkspaceError]:
    raise NotImplementedError
