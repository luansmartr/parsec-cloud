// Parsec Cloud (https://parsec.cloud) Copyright (c) BUSL-1.1 2016-present Scille SAS

import { libparsec, WorkspaceStopError } from '@/plugins/libparsec';
import {
  Result,
  WorkspaceInfo,
  ClientListWorkspacesError,
  WorkspaceID,
  WorkspaceRole,
  UserTuple,
  GetWorkspaceNameError,
  WorkspaceName,
  ClientCreateWorkspaceError,
  ClientListWorkspaceUsersError,
  ClientShareWorkspaceError,
  UserID,
  WorkspaceHandle,
  ClientStartWorkspaceError,
} from '@/parsec/types';
import { getParsecHandle } from '@/parsec/routing';
import { getClientInfo } from '@/parsec/functions';
import { DateTime } from 'luxon';

export async function listWorkspaces(): Promise<Result<Array<WorkspaceInfo>, ClientListWorkspacesError>> {
  const handle = getParsecHandle();

  if (handle !== null && window.isDesktop()) {
    const result = await libparsec.clientListWorkspaces(handle);

    if (result.ok) {
      const returnValue: Array<WorkspaceInfo> = [];
      for (let i = 0; i < result.value.length; i++) {
        const sharingResult = await getWorkspaceSharing(result.value[i].id, false);
        const info: WorkspaceInfo = {
          id: result.value[i].id,
          name: result.value[i].name,
          selfRole: result.value[i].selfRole,
          sharing: [],
          size: 0,
          lastUpdated: DateTime.now(),
          availableOffline: false,
        };
        if (sharingResult.ok) {
          info.sharing = sharingResult.value;
        }
        returnValue.push(info);
      }
      return {ok: true, value: returnValue};
    } else {
      return result;
    }
  } else {
    const value: Array<WorkspaceInfo> = [{
      'id': '1', 'name': 'Trademeet', 'selfRole': WorkspaceRole.Owner, size: 934_583, lastUpdated: DateTime.now().minus(2000),
      availableOffline: false, sharing: [],
    }, {
      'id': '2', 'name': 'The Copper Coronet', 'selfRole': WorkspaceRole.Manager, size: 3_489_534_274, lastUpdated: DateTime.now(),
      availableOffline: false, sharing: [],
    }];

    for (let i = 0; i < value.length; i++) {
      const result = await getWorkspaceSharing(value[i].id, false);
      if (result.ok) {
        value[i].sharing = result.value;
      }
    }

    return {ok: true, value: value};
  }
}

export async function createWorkspace(name: WorkspaceName): Promise<Result<WorkspaceID, ClientCreateWorkspaceError>> {
  const handle = getParsecHandle();

  if (handle !== null && window.isDesktop()) {
    return await libparsec.clientCreateWorkspace(handle, name);
  } else {
    return { ok: true, value: '1337' };
  }
}

export async function getWorkspaceName(workspaceId: WorkspaceID): Promise<Result<WorkspaceName, GetWorkspaceNameError>> {
  const handle = getParsecHandle();

  if (handle !== null && window.isDesktop()) {
    const result = await libparsec.clientListWorkspaces(handle);
    if (result.ok) {
      const workspace = result.value.find((info) => {
        if (info.id === workspaceId) {
          return true;
        }
        return false;
      });
      if (workspace) {
        return {ok: true, value: workspace.name};
      }
    }
    return {ok: false, error: {tag: 'NotFound'}};
  } else {
    if (workspaceId === '1') {
      return {ok: true, value: 'Trademeet'};
    } else if (workspaceId === '2') {
      return {ok: true, value: 'The Copper Coronet'};
    } else {
      return {ok: true, value: 'My Workspace'};
    }
  }
}

export async function getWorkspaceSharing(workspaceId: WorkspaceID, includeAllUsers = false, includeSelf = false):
  Promise<Result<Array<[UserTuple, WorkspaceRole | null]>, ClientListWorkspaceUsersError>> {
  const handle = getParsecHandle();

  if (handle !== null && window.isDesktop()) {
    let selfId: UserID | null = null;

    if (!includeSelf) {
      const clientResult = await getClientInfo();
      if (clientResult.ok) {
        selfId = clientResult.value.userId;
      }
    }

    const result = await libparsec.clientListWorkspaceUsers(handle, workspaceId);
    if (result.ok) {
      const value: Array<[UserTuple, WorkspaceRole | null]> = [];

      for (const sharing of result.value) {
        if (includeSelf || (!includeSelf && selfId !== sharing.userId)) {
          value.push([{id: sharing.userId, humanHandle: sharing.humanHandle || {label: sharing.userId, email: ''}}, sharing.role]);
        }
      }
      if (includeAllUsers) {
        const usersResult = await libparsec.clientListUsers(handle, true);
        if (usersResult.ok) {
          for (const user of usersResult.value) {
            if (!value.find((item) => item[0].id === user.id) && (includeSelf || (!includeSelf && user.id !== selfId))) {
              value.push([{id: user.id, humanHandle: user.humanHandle || {label: user.id, email: ''}}, null]);
            }
          }
        }
      }
      return {ok: true, value: value};
    }
    return {ok: false, error: result.error};
  } else {
    const value: Array<[UserTuple, WorkspaceRole | null]> = [[
      // cspell:disable-next-line
      {id: '1', humanHandle: {label: 'Korgan Bloodaxe', email: 'korgan@gmail.com'}}, WorkspaceRole.Reader,
    ], [
      // cspell:disable-next-line
      {id: '2', humanHandle: {label: 'Cernd', email: 'cernd@gmail.com'}}, WorkspaceRole.Contributor,
    ]];

    if (includeSelf) {
      value.push([{id: 'me', humanHandle: {email: 'user@host.com', label: 'Gordon Freeman'}}, WorkspaceRole.Owner]);
    }

    if (includeAllUsers) {
      // cspell:disable-next-line
      value.push([{id: '3', humanHandle: {label: 'Jaheira', email: 'jaheira@gmail.com'}}, null]);
    }

    return {ok: true, value: value};
  }
}

export async function shareWorkspace(workspaceId: WorkspaceID, userId: UserID, role: WorkspaceRole | null):
  Promise<Result<null, ClientShareWorkspaceError>> {
  const handle = getParsecHandle();

  if (handle !== null && window.isDesktop()) {
    return await libparsec.clientShareWorkspace(handle, workspaceId, userId, role);
  } else {
    return {ok: true, value: null};
  }
}

export async function startWorkspace(workspaceId: WorkspaceID): Promise<Result<WorkspaceHandle, ClientStartWorkspaceError>> {
  const handle = getParsecHandle();

  if (handle !== null && window.isDesktop()) {
    return await libparsec.clientStartWorkspace(handle, workspaceId);
  } else {
    return {ok: true, value: 1337};
  }
}

export async function stopWorkspace(workspaceHandle: WorkspaceHandle): Promise<Result<null, WorkspaceStopError>> {
  const handle = getParsecHandle();

  if (handle !== null && window.isDesktop()) {
    return await libparsec.workspaceStop(workspaceHandle);
  } else {
    return {ok: true, value: null};
  }
}
