# Parsec Cloud (https://parsec.cloud) Copyright (c) BUSL-1.1 2016-present Scille SAS
from __future__ import annotations

import smtplib
import ssl
import sys
import tempfile
from collections import defaultdict
from email.header import Header
from email.message import Message
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Set, Type, Union, cast

import attr
import trio
from structlog import get_logger

from parsec._parsec import (
    BackendEvent,
    BackendEventInviteConduitUpdated,
    BackendEventInviteStatusChanged,
    BackendInvitationAddr,
    DateTime,
    HashDigest,
    HumanHandle,
    InvitationStatus,
    InvitationToken,
    InvitationType,
    OrganizationID,
    PublicKey,
    UserID,
    UserProfile,
    authenticated_cmds,
    invited_cmds,
)
from parsec.backend.config import BackendConfig, EmailConfig, MockedEmailConfig, SmtpEmailConfig
from parsec.backend.templates import get_template
from parsec.backend.utils import api
from parsec.event_bus import EventBus, EventFilterCallback

if TYPE_CHECKING:
    from parsec.backend.client_context import AuthenticatedClientContext, InvitedClientContext


InvitationDeletedReason = authenticated_cmds.latest.invite_delete.InvitationDeletedReason
logger = get_logger()


class CloseInviteConnection(Exception):
    pass


class InvitationError(Exception):
    pass


class InvitationNotFoundError(InvitationError):
    pass


class InvitationAlreadyDeletedError(InvitationError):
    pass


class InvitationInvalidStateError(InvitationError):
    pass


class InvitationAlreadyMemberError(InvitationError):
    pass


class InvitationEmailConfigError(InvitationError):
    pass


class InvitationEmailRecipientError(InvitationError):
    pass


class ConduitState(Enum):
    STATE_1_WAIT_PEERS = "1_WAIT_PEERS"
    STATE_2_1_CLAIMER_HASHED_NONCE = "2_1_CLAIMER_HASHED_NONCE"
    STATE_2_2_GREETER_NONCE = "2_2_GREETER_NONCE"
    STATE_2_3_CLAIMER_NONCE = "2_3_CLAIMER_NONCE"
    STATE_3_1_CLAIMER_TRUST = "3_1_CLAIMER_TRUST"
    STATE_3_2_GREETER_TRUST = "3_2_GREETER_TRUST"
    STATE_4_COMMUNICATE = "4_COMMUNICATE"


NEXT_CONDUIT_STATE = {
    ConduitState.STATE_1_WAIT_PEERS: ConduitState.STATE_2_1_CLAIMER_HASHED_NONCE,
    ConduitState.STATE_2_1_CLAIMER_HASHED_NONCE: ConduitState.STATE_2_2_GREETER_NONCE,
    ConduitState.STATE_2_2_GREETER_NONCE: ConduitState.STATE_2_3_CLAIMER_NONCE,
    ConduitState.STATE_2_3_CLAIMER_NONCE: ConduitState.STATE_3_1_CLAIMER_TRUST,
    ConduitState.STATE_3_1_CLAIMER_TRUST: ConduitState.STATE_3_2_GREETER_TRUST,
    ConduitState.STATE_3_2_GREETER_TRUST: ConduitState.STATE_4_COMMUNICATE,
    ConduitState.STATE_4_COMMUNICATE: ConduitState.STATE_4_COMMUNICATE,
}


@attr.s(slots=True, frozen=True, auto_attribs=True)
class ConduitListenCtx:
    organization_id: OrganizationID
    greeter: UserID | None
    token: InvitationToken
    state: ConduitState
    payload: bytes
    peer_payload: bytes | None

    @property
    def is_greeter(self) -> bool:
        return self.greeter is not None


@attr.s(slots=True, frozen=True, auto_attribs=True)
class UserInvitation:
    TYPE = InvitationType.USER
    greeter_user_id: UserID
    greeter_human_handle: HumanHandle | None
    claimer_email: str
    token: InvitationToken = attr.ib(factory=InvitationToken.new)
    created_on: DateTime = attr.ib(factory=DateTime.now)
    status: InvitationStatus = InvitationStatus.IDLE

    def evolve(self, **kwargs: Any) -> UserInvitation:
        return attr.evolve(self, **kwargs)


@attr.s(slots=True, frozen=True, auto_attribs=True)
class DeviceInvitation:
    TYPE = InvitationType.DEVICE
    greeter_user_id: UserID
    greeter_human_handle: HumanHandle | None
    token: InvitationToken = attr.ib(factory=InvitationToken.new)
    created_on: DateTime = attr.ib(factory=DateTime.now)
    status: InvitationStatus = InvitationStatus.IDLE

    def evolve(self, **kwargs: Any) -> DeviceInvitation:
        return attr.evolve(self, **kwargs)


Invitation = Union[UserInvitation, DeviceInvitation]


def generate_invite_email(
    from_addr: str,
    to_addr: str,
    reply_to: str | None,
    greeter_name: str | None,  # None for device invitation
    organization_id: OrganizationID,
    invitation_url: str,
    backend_url: str,
) -> Message:
    # Quick fix to have a similar behavior between Rust and Python
    if backend_url.endswith("/"):
        backend_url = backend_url[:-1]
    html = get_template("invitation_mail.html").render(
        greeter=greeter_name,
        organization_id=organization_id.str,
        invitation_url=invitation_url,
        backend_url=backend_url,
    )
    text = get_template("invitation_mail.txt").render(
        greeter=greeter_name,
        organization_id=organization_id.str,
        invitation_url=invitation_url,
        backend_url=backend_url,
    )

    # mail settings
    message = MIMEMultipart("alternative")
    if greeter_name:
        message["Subject"] = f"[Parsec] { greeter_name } invited you to { organization_id.str }"
    else:
        message["Subject"] = f"[Parsec] New device invitation to { organization_id.str }"
    message["From"] = from_addr
    message["To"] = to_addr
    if reply_to is not None and greeter_name is not None:
        # Contrary to the other address fields, the greeter name can include non-ascii characters
        # Example: "Jean-José" becomes "=?utf-8?q?Jean-Jos=C3=A9?="
        encoded_greeter_name = Header(greeter_name.encode("utf-8"), "utf-8").encode()
        message["Reply-To"] = f"{encoded_greeter_name} <{reply_to}>"

    # Turn parts into MIMEText objects
    part1 = MIMEText(text, "plain")
    part2 = MIMEText(html, "html")

    # Add HTML/plain-text parts to MIMEMultipart message
    # The email client will try to render the last part first
    message.attach(part1)
    message.attach(part2)

    return message


async def _smtp_send_mail(email_config: SmtpEmailConfig, to_addr: str, message: Message) -> None:
    def _do() -> None:
        try:
            context = ssl.create_default_context()
            if email_config.use_ssl:
                server: Union[smtplib.SMTP, smtplib.SMTP_SSL] = smtplib.SMTP_SSL(
                    email_config.host, email_config.port, context=context
                )
            else:
                server = smtplib.SMTP(email_config.host, email_config.port)

            with server:
                if email_config.use_tls and not email_config.use_ssl:
                    if server.starttls(context=context)[0] != 220:
                        logger.warning("Email TLS connection isn't encrypted")
                if email_config.host_user and email_config.host_password:
                    server.login(email_config.host_user, email_config.host_password)
                server.sendmail(email_config.sender, to_addr, message.as_string())

        except smtplib.SMTPRecipientsRefused as e:
            raise InvitationEmailRecipientError from e
        except smtplib.SMTPException as e:
            logger.warning("SMTP error", exc_info=e, to_addr=to_addr, subject=message["Subject"])
            raise InvitationEmailConfigError from e

    await trio.to_thread.run_sync(_do)


async def _mocked_send_mail(
    email_config: MockedEmailConfig, to_addr: str, message: Message
) -> None:
    def _do() -> None:
        tmpfile_fd, tmpfile_path = tempfile.mkstemp(
            prefix="tmp-email-", suffix=".html", dir=email_config.tmpdir
        )
        tmpfile = open(tmpfile_path, "w")
        tmpfile.write(message.as_string())
        print(
            f"""\
A request to send an e-mail to {to_addr} has been triggered and mocked.
The mail file can be found here: {tmpfile.name}\n""",
            tmpfile.name,
            file=sys.stderr,
        )

    await trio.to_thread.run_sync(_do)


async def send_email(email_config: EmailConfig, to_addr: str, message: Message) -> None:
    if isinstance(email_config, SmtpEmailConfig):
        await _smtp_send_mail(email_config, to_addr, message)
    else:
        await _mocked_send_mail(email_config, to_addr, message)


class BaseInviteComponent:
    def __init__(self, event_bus: EventBus, config: BackendConfig):
        self._event_bus = event_bus
        self._config = config
        # We use the `invite.status_changed` event to keep a list of all the
        # invitation claimers connected across all backends.
        #
        # This is useful to display the invitations ready to be greeted.
        # Note we rely on a per-backend list in memory instead of storing this
        # information in database so that we default to no claimer present
        # (which is the most likely when a backend is restarted) .
        #
        # However there are multiple ways this list can go out of sync:
        # - a claimer can be connected to a backend, then another backend starts
        # - the backend the claimer is connected to crashes without being able
        #   to notify the other backends
        # - a claimer open multiple connections at the same time, then is
        #   considered disconnected as soon as he closes one of his connections
        #
        # This is considered "fine enough" given all the claimer has to do
        # to fix this is to retry a connection, which precisely the kind of
        # "I.T., have you tried to turn it off and on again ?" a human is
        # expected to do ;-)
        self._claimers_ready: Dict[OrganizationID, Set[InvitationToken]] = defaultdict(set)

        def _on_status_changed(
            event: Type[BackendEvent], event_id: str, payload: BackendEventInviteStatusChanged
        ) -> None:
            if payload.status == InvitationStatus.READY:
                self._claimers_ready[payload.organization_id].add(payload.token)
            else:  # Invitation deleted or back to idle
                self._claimers_ready[payload.organization_id].discard(payload.token)

        self._event_bus.connect(
            BackendEventInviteStatusChanged,
            _on_status_changed,  # type: ignore[arg-type]
        )

    @api
    async def api_invite_new(
        self, client_ctx: AuthenticatedClientContext, req: authenticated_cmds.latest.invite_new.Req
    ) -> authenticated_cmds.latest.invite_new.Rep:
        # Define helper
        def _to_http_redirection_url(
            client_ctx: AuthenticatedClientContext,
            invitation: Union[UserInvitation, DeviceInvitation],
        ) -> str:
            assert self._config.backend_addr
            return BackendInvitationAddr.build(
                backend_addr=self._config.backend_addr,
                organization_id=client_ctx.organization_id,
                invitation_type=invitation.TYPE,
                token=invitation.token,
            ).to_http_redirection_url()

        # Create new user / new device
        req_unit = req.unit
        req_unit_send_email: bool
        if isinstance(req_unit, authenticated_cmds.latest.invite_new.UserOrDeviceUser):
            req_unit_send_email = req_unit.send_email
            if client_ctx.profile != UserProfile.ADMIN:
                return authenticated_cmds.latest.invite_new.RepNotAllowed()
            try:
                invitation: UserInvitation | DeviceInvitation = await self.new_for_user(
                    organization_id=client_ctx.organization_id,
                    greeter_user_id=client_ctx.user_id,
                    claimer_email=req_unit.claimer_email,
                )
            except InvitationAlreadyMemberError:
                return authenticated_cmds.latest.invite_new.RepAlreadyMember()

        else:  # Device
            assert isinstance(req_unit, authenticated_cmds.latest.invite_new.UserOrDeviceDevice)
            req_unit_send_email = req_unit.send_email
            if req_unit.send_email and not client_ctx.human_handle:
                return authenticated_cmds.latest.invite_new.RepNotAvailable()

            invitation = await self.new_for_device(
                organization_id=client_ctx.organization_id,
                greeter_user_id=client_ctx.user_id,
            )

        # No need to send email, we're done
        if not req_unit_send_email:
            # Note: before parsec v2.13.0, we used to reply with a missing `email_sent` field in this case.
            # However, we'd rather limit the use of missing fields to compatibility use cases (e.g when a
            # field has been added in a new version but does not exist in older versions). In this case, we
            # can replace the missing field with `SUCCESS` without breaking compatibility with older clients
            # since they also choose `SUCCESS` as value when getting an `AttributeError` on the reply.
            return authenticated_cmds.latest.invite_new.RepOk(
                invitation.token,
                authenticated_cmds.latest.invite_new.InvitationEmailSentStatus.SUCCESS,
            )

        # Backend address not configured, we won't be able to send the email
        if not self._config.backend_addr:
            return authenticated_cmds.latest.invite_new.RepOk(
                invitation.token,
                authenticated_cmds.latest.invite_new.InvitationEmailSentStatus.NOT_AVAILABLE,
            )

        # Generate email message
        if isinstance(req_unit, authenticated_cmds.latest.invite_new.UserOrDeviceUser):
            assert isinstance(invitation, UserInvitation)
            to_addr = invitation.claimer_email
            if client_ctx.human_handle:
                greeter_name = client_ctx.human_handle.label
                reply_to = client_ctx.human_handle.email
            else:
                greeter_name = client_ctx.user_id.str
                reply_to = None
            message = generate_invite_email(
                from_addr=self._config.email_config.sender,
                to_addr=invitation.claimer_email,
                greeter_name=greeter_name,
                reply_to=reply_to,
                organization_id=client_ctx.organization_id,
                invitation_url=_to_http_redirection_url(client_ctx, invitation),
                backend_url=self._config.backend_addr.to_http_domain_url(),
            )
        else:  # Device
            assert isinstance(req_unit, authenticated_cmds.latest.invite_new.UserOrDeviceDevice)
            assert isinstance(invitation, DeviceInvitation)
            assert client_ctx.human_handle is not None
            to_addr = client_ctx.human_handle.email
            message = generate_invite_email(
                from_addr=self._config.email_config.sender,
                to_addr=to_addr,
                greeter_name=None,
                reply_to=None,
                organization_id=client_ctx.organization_id,
                invitation_url=_to_http_redirection_url(client_ctx, invitation),
                backend_url=self._config.backend_addr.to_http_domain_url(),
            )

        # Send the email
        try:
            await send_email(
                email_config=self._config.email_config,
                to_addr=to_addr,
                message=message,
            )
        except InvitationEmailRecipientError:
            return authenticated_cmds.latest.invite_new.RepOk(
                invitation.token,
                authenticated_cmds.latest.invite_new.InvitationEmailSentStatus.BAD_RECIPIENT,
            )
        except InvitationEmailConfigError:
            return authenticated_cmds.latest.invite_new.RepOk(
                invitation.token,
                authenticated_cmds.latest.invite_new.InvitationEmailSentStatus.NOT_AVAILABLE,
            )
        except Exception:
            # Fail-safe: since the device/user has been created, we don't want to fail too hard
            logger.exception("Unexpected exception while sending an email")
            return authenticated_cmds.latest.invite_new.RepOk(
                invitation.token,
                authenticated_cmds.latest.invite_new.InvitationEmailSentStatus.NOT_AVAILABLE,
            )

        # The email has been successfully sent
        return authenticated_cmds.latest.invite_new.RepOk(
            invitation.token, authenticated_cmds.latest.invite_new.InvitationEmailSentStatus.SUCCESS
        )

    @api
    async def api_invite_delete(
        self,
        client_ctx: AuthenticatedClientContext,
        req: authenticated_cmds.latest.invite_delete.Req,
    ) -> authenticated_cmds.latest.invite_delete.Rep:
        try:
            await self.delete(
                organization_id=client_ctx.organization_id,
                greeter=client_ctx.user_id,
                token=req.token,
                on=DateTime.now(),
                reason=req.reason,
            )

        except InvitationNotFoundError:
            return authenticated_cmds.latest.invite_delete.RepNotFound()

        except InvitationAlreadyDeletedError:
            return authenticated_cmds.latest.invite_delete.RepAlreadyDeleted()

        return authenticated_cmds.latest.invite_delete.RepOk()

    @api
    async def api_invite_list(
        self, client_ctx: AuthenticatedClientContext, req: authenticated_cmds.latest.invite_list.Req
    ) -> authenticated_cmds.latest.invite_list.Rep:
        invitations = await self.list(
            organization_id=client_ctx.organization_id, greeter=client_ctx.user_id
        )

        return authenticated_cmds.latest.invite_list.RepOk(
            [
                authenticated_cmds.latest.invite_list.InviteListItemUser(
                    item.token, item.created_on, item.claimer_email, item.status
                )
                if isinstance(item, UserInvitation)
                else authenticated_cmds.latest.invite_list.InviteListItemDevice(
                    item.token, item.created_on, item.status
                )
                for item in invitations
            ]
        )

    @api
    async def api_invite_info(
        self, client_ctx: InvitedClientContext, req: invited_cmds.latest.invite_info.Req
    ) -> invited_cmds.latest.invite_info.Rep:
        # Invitation has already been fetched during handshake, this
        # means we don't have to access the database at all here.
        # Not accessing the database also means we cannot detect if invitation
        # has been deleted but it's no big deal given we don't modify anything !
        # (and the connection will eventually be closed by backend event anyway)
        invitation = client_ctx.invitation
        if isinstance(invitation, UserInvitation):
            return invited_cmds.latest.invite_info.RepOk(
                invited_cmds.latest.invite_info.UserOrDeviceUser(
                    claimer_email=invitation.claimer_email,
                    greeter_user_id=invitation.greeter_user_id,
                    greeter_human_handle=invitation.greeter_human_handle,
                )
            )
        else:  # DeviceInvitation
            return invited_cmds.latest.invite_info.RepOk(
                invited_cmds.latest.invite_info.UserOrDeviceDevice(
                    greeter_user_id=invitation.greeter_user_id,
                    greeter_human_handle=invitation.greeter_human_handle,
                )
            )

    @api
    async def api_invite_1_claimer_wait_peer(
        self,
        client_ctx: InvitedClientContext,
        req: invited_cmds.latest.invite_1_claimer_wait_peer.Req,
    ) -> invited_cmds.latest.invite_1_claimer_wait_peer.Rep:
        """
        Raises:
            CloseInviteConnection
        """
        try:
            greeter_public_key = await self.conduit_exchange(
                organization_id=client_ctx.organization_id,
                greeter=None,
                token=client_ctx.invitation.token,
                state=ConduitState.STATE_1_WAIT_PEERS,
                payload=req.claimer_public_key.encode(),
            )

        except InvitationAlreadyDeletedError as exc:
            # Notify parent that the connection shall be close because the invitation token is no longer valid.
            raise CloseInviteConnection from exc

        except InvitationNotFoundError:
            return invited_cmds.latest.invite_1_claimer_wait_peer.RepNotFound()

        except InvitationInvalidStateError:
            return invited_cmds.latest.invite_1_claimer_wait_peer.RepInvalidState()

        return invited_cmds.latest.invite_1_claimer_wait_peer.RepOk(PublicKey(greeter_public_key))

    @api
    async def api_invite_1_greeter_wait_peer(
        self,
        client_ctx: AuthenticatedClientContext,
        req: authenticated_cmds.latest.invite_1_greeter_wait_peer.Req,
    ) -> authenticated_cmds.latest.invite_1_greeter_wait_peer.Rep:
        try:
            claimer_public_key_raw = await self.conduit_exchange(
                organization_id=client_ctx.organization_id,
                greeter=client_ctx.user_id,
                token=req.token,
                state=ConduitState.STATE_1_WAIT_PEERS,
                payload=req.greeter_public_key.encode(),
            )

        except InvitationNotFoundError:
            return authenticated_cmds.latest.invite_1_greeter_wait_peer.RepNotFound()

        except InvitationAlreadyDeletedError:
            return authenticated_cmds.latest.invite_1_greeter_wait_peer.RepAlreadyDeleted()

        except InvitationInvalidStateError:
            return authenticated_cmds.latest.invite_1_greeter_wait_peer.RepInvalidState()

        return authenticated_cmds.latest.invite_1_greeter_wait_peer.RepOk(
            PublicKey(claimer_public_key_raw)
        )

    @api
    async def api_invite_2a_claimer_send_hash_nonce(
        self,
        client_ctx: InvitedClientContext,
        req: invited_cmds.latest.invite_2a_claimer_send_hashed_nonce.Req,
    ) -> invited_cmds.latest.invite_2a_claimer_send_hashed_nonce.Rep:
        """
        Raises:
            CloseInviteConnection
        """
        try:
            await self.conduit_exchange(
                organization_id=client_ctx.organization_id,
                greeter=None,
                token=client_ctx.invitation.token,
                state=ConduitState.STATE_2_1_CLAIMER_HASHED_NONCE,
                payload=req.claimer_hashed_nonce.digest,
            )

            greeter_nonce = await self.conduit_exchange(
                organization_id=client_ctx.organization_id,
                greeter=None,
                token=client_ctx.invitation.token,
                state=ConduitState.STATE_2_2_GREETER_NONCE,
                payload=b"",
            )

        except InvitationAlreadyDeletedError as exc:
            # Notify parent that the connection shall be close because the invitation token is no longer valid.
            raise CloseInviteConnection from exc

        except InvitationNotFoundError:
            return invited_cmds.latest.invite_2a_claimer_send_hashed_nonce.RepNotFound()

        except InvitationInvalidStateError:
            return invited_cmds.latest.invite_2a_claimer_send_hashed_nonce.RepInvalidState()

        return invited_cmds.latest.invite_2a_claimer_send_hashed_nonce.RepOk(greeter_nonce)

    @api
    async def api_invite_2a_greeter_get_hashed_nonce(
        self,
        client_ctx: AuthenticatedClientContext,
        req: authenticated_cmds.latest.invite_2a_greeter_get_hashed_nonce.Req,
    ) -> authenticated_cmds.latest.invite_2a_greeter_get_hashed_nonce.Rep:
        try:
            claimer_hashed_nonce_raw = await self.conduit_exchange(
                organization_id=client_ctx.organization_id,
                greeter=client_ctx.user_id,
                token=req.token,
                state=ConduitState.STATE_2_1_CLAIMER_HASHED_NONCE,
                payload=b"",
            )
            # Should not fail given data is check on DB insertion
            claimer_hashed_nonce = HashDigest(claimer_hashed_nonce_raw)

        except InvitationNotFoundError:
            return authenticated_cmds.latest.invite_2a_greeter_get_hashed_nonce.RepNotFound()

        except InvitationAlreadyDeletedError:
            return authenticated_cmds.latest.invite_2a_greeter_get_hashed_nonce.RepAlreadyDeleted()

        except InvitationInvalidStateError:
            return authenticated_cmds.latest.invite_2a_greeter_get_hashed_nonce.RepInvalidState()

        return authenticated_cmds.latest.invite_2a_greeter_get_hashed_nonce.RepOk(
            claimer_hashed_nonce
        )

    @api
    async def api_invite_2b_greeter_send_nonce(
        self,
        client_ctx: AuthenticatedClientContext,
        req: authenticated_cmds.latest.invite_2b_greeter_send_nonce.Req,
    ) -> authenticated_cmds.latest.invite_2b_greeter_send_nonce.Rep:
        try:
            await self.conduit_exchange(
                organization_id=client_ctx.organization_id,
                greeter=client_ctx.user_id,
                token=req.token,
                state=ConduitState.STATE_2_2_GREETER_NONCE,
                payload=req.greeter_nonce,
            )

            claimer_nonce = await self.conduit_exchange(
                organization_id=client_ctx.organization_id,
                greeter=client_ctx.user_id,
                token=req.token,
                state=ConduitState.STATE_2_3_CLAIMER_NONCE,
                payload=b"",
            )

        except InvitationNotFoundError:
            return authenticated_cmds.latest.invite_2b_greeter_send_nonce.RepNotFound()

        except InvitationAlreadyDeletedError:
            return authenticated_cmds.latest.invite_2b_greeter_send_nonce.RepAlreadyDeleted()

        except InvitationInvalidStateError:
            return authenticated_cmds.latest.invite_2b_greeter_send_nonce.RepInvalidState()

        return authenticated_cmds.latest.invite_2b_greeter_send_nonce.RepOk(claimer_nonce)

    @api
    async def api_invite_2b_claimer_send_nonce(
        self,
        client_ctx: InvitedClientContext,
        req: invited_cmds.latest.invite_2b_claimer_send_nonce.Req,
    ) -> invited_cmds.latest.invite_2b_claimer_send_nonce.Rep:
        """
        Raises:
            CloseInviteConnection
        """
        try:
            await self.conduit_exchange(
                organization_id=client_ctx.organization_id,
                greeter=None,
                token=client_ctx.invitation.token,
                state=ConduitState.STATE_2_3_CLAIMER_NONCE,
                payload=req.claimer_nonce,
            )

        except InvitationAlreadyDeletedError as exc:
            # Notify parent that the connection shall be close because the invitation token is no longer valid.
            raise CloseInviteConnection from exc

        except InvitationNotFoundError:
            return invited_cmds.latest.invite_2b_claimer_send_nonce.RepNotFound()

        except InvitationInvalidStateError:
            return invited_cmds.latest.invite_2b_claimer_send_nonce.RepInvalidState()

        return invited_cmds.latest.invite_2b_claimer_send_nonce.RepOk()

    @api
    async def api_invite_3a_greeter_wait_peer_trust(
        self,
        client_ctx: AuthenticatedClientContext,
        req: authenticated_cmds.latest.invite_3a_greeter_wait_peer_trust.Req,
    ) -> authenticated_cmds.latest.invite_3a_greeter_wait_peer_trust.Rep:
        try:
            await self.conduit_exchange(
                organization_id=client_ctx.organization_id,
                greeter=client_ctx.user_id,
                token=req.token,
                state=ConduitState.STATE_3_1_CLAIMER_TRUST,
                payload=b"",
            )

        except InvitationNotFoundError:
            return authenticated_cmds.latest.invite_3a_greeter_wait_peer_trust.RepNotFound()

        except InvitationAlreadyDeletedError:
            return authenticated_cmds.latest.invite_3a_greeter_wait_peer_trust.RepAlreadyDeleted()

        except InvitationInvalidStateError:
            return authenticated_cmds.latest.invite_3a_greeter_wait_peer_trust.RepInvalidState()

        return authenticated_cmds.latest.invite_3a_greeter_wait_peer_trust.RepOk()

    @api
    async def api_invite_3b_claimer_wait_peer_trust(
        self,
        client_ctx: InvitedClientContext,
        req: invited_cmds.latest.invite_3b_claimer_wait_peer_trust.Req,
    ) -> invited_cmds.latest.invite_3b_claimer_wait_peer_trust.Rep:
        """
        Raises:
            CloseInviteConnection
        """
        try:
            await self.conduit_exchange(
                organization_id=client_ctx.organization_id,
                greeter=None,
                token=client_ctx.invitation.token,
                state=ConduitState.STATE_3_2_GREETER_TRUST,
                payload=b"",
            )

        except InvitationAlreadyDeletedError as exc:
            # Notify parent that the connection shall be close because the invitation token is no longer valid.
            raise CloseInviteConnection from exc

        except InvitationNotFoundError:
            return invited_cmds.latest.invite_3b_claimer_wait_peer_trust.RepNotFound()

        except InvitationInvalidStateError:
            return invited_cmds.latest.invite_3b_claimer_wait_peer_trust.RepInvalidState()

        return invited_cmds.latest.invite_3b_claimer_wait_peer_trust.RepOk()

    @api
    async def api_invite_3b_greeter_signify_trust(
        self,
        client_ctx: AuthenticatedClientContext,
        req: authenticated_cmds.latest.invite_3b_greeter_signify_trust.Req,
    ) -> authenticated_cmds.latest.invite_3b_greeter_signify_trust.Rep:
        try:
            await self.conduit_exchange(
                organization_id=client_ctx.organization_id,
                greeter=client_ctx.user_id,
                token=req.token,
                state=ConduitState.STATE_3_2_GREETER_TRUST,
                payload=b"",
            )

        except InvitationNotFoundError:
            return authenticated_cmds.latest.invite_3b_greeter_signify_trust.RepNotFound()

        except InvitationAlreadyDeletedError:
            return authenticated_cmds.latest.invite_3b_greeter_signify_trust.RepAlreadyDeleted()

        except InvitationInvalidStateError:
            return authenticated_cmds.latest.invite_3b_greeter_signify_trust.RepInvalidState()

        return authenticated_cmds.latest.invite_3b_greeter_signify_trust.RepOk()

    @api
    async def api_invite_3a_claimer_signify_trust(
        self,
        client_ctx: InvitedClientContext,
        req: invited_cmds.latest.invite_3a_claimer_signify_trust.Req,
    ) -> invited_cmds.latest.invite_3a_claimer_signify_trust.Rep:
        """
        Raises:
            CloseInviteConnection
        """
        try:
            await self.conduit_exchange(
                organization_id=client_ctx.organization_id,
                greeter=None,
                token=client_ctx.invitation.token,
                state=ConduitState.STATE_3_1_CLAIMER_TRUST,
                payload=b"",
            )

        except InvitationAlreadyDeletedError as exc:
            # Notify parent that the connection shall be close because the invitation token is no longer valid.
            raise CloseInviteConnection from exc

        except InvitationNotFoundError:
            return invited_cmds.latest.invite_3a_claimer_signify_trust.RepNotFound()

        except InvitationInvalidStateError:
            return invited_cmds.latest.invite_3a_claimer_signify_trust.RepInvalidState()

        return invited_cmds.latest.invite_3a_claimer_signify_trust.RepOk()

    @api
    async def api_invite_4_greeter_communicate(
        self,
        client_ctx: AuthenticatedClientContext,
        req: authenticated_cmds.latest.invite_4_greeter_communicate.Req,
    ) -> authenticated_cmds.latest.invite_4_greeter_communicate.Rep:
        try:
            answer_payload = await self.conduit_exchange(
                organization_id=client_ctx.organization_id,
                greeter=client_ctx.user_id,
                token=req.token,
                state=ConduitState.STATE_4_COMMUNICATE,
                payload=req.payload,
            )

        except InvitationNotFoundError:
            return authenticated_cmds.latest.invite_4_greeter_communicate.RepNotFound()

        except InvitationAlreadyDeletedError:
            return authenticated_cmds.latest.invite_4_greeter_communicate.RepAlreadyDeleted()

        except InvitationInvalidStateError:
            return authenticated_cmds.latest.invite_4_greeter_communicate.RepInvalidState()

        return authenticated_cmds.latest.invite_4_greeter_communicate.RepOk(answer_payload)

    @api
    async def api_invite_4_claimer_communicate(
        self,
        client_ctx: InvitedClientContext,
        req: invited_cmds.latest.invite_4_claimer_communicate.Req,
    ) -> invited_cmds.latest.invite_4_claimer_communicate.Rep:
        """
        Raises:
            CloseInviteConnection
        """
        try:
            answer_payload = await self.conduit_exchange(
                organization_id=client_ctx.organization_id,
                greeter=None,
                token=client_ctx.invitation.token,
                state=ConduitState.STATE_4_COMMUNICATE,
                payload=req.payload,
            )

        except InvitationAlreadyDeletedError as exc:
            # Notify parent that the connection shall be close because the invitation token is no longer valid.
            raise CloseInviteConnection from exc

        except InvitationNotFoundError:
            return invited_cmds.latest.invite_4_claimer_communicate.RepNotFound()

        except InvitationInvalidStateError:
            return invited_cmds.latest.invite_4_claimer_communicate.RepInvalidState()

        return invited_cmds.latest.invite_4_claimer_communicate.RepOk(answer_payload)

    async def conduit_exchange(
        self,
        organization_id: OrganizationID,
        greeter: UserID | None,
        token: InvitationToken,
        state: ConduitState,
        payload: bytes,
    ) -> bytes:
        # Conduit exchange is done in two steps:
        # First we "talk" by providing our payload and retrieve the peer's
        # payload if he has talked prior to us.
        # Then we "listen" by waiting for the peer to provide his payload if we
        # have talked first, or to confirm us it has received our payload if we
        # have talked after him.
        filter_organization_id = organization_id
        filter_token = token

        def _event_filter(
            event: Type[BackendEvent],
            event_id: str,
            payload: BackendEventInviteConduitUpdated | BackendEventInviteStatusChanged,
        ) -> bool:
            return (
                payload.organization_id == filter_organization_id and payload.token == filter_token
            )

        with self._event_bus.waiter_on_first(
            cast(Any, BackendEventInviteConduitUpdated),
            cast(Any, BackendEventInviteStatusChanged),
            filter=cast(EventFilterCallback, _event_filter),
        ) as waiter:
            listen_ctx = await self._conduit_talk(organization_id, greeter, token, state, payload)

            # Unlike what it name may imply, `_conduit_listen` doesn't wait for the peer
            # to answer (it returns `None` instead), so we wait for some events to occur
            # before calling:
            # - INVITE_CONDUIT_UPDATED: Triggered when the peer has completed it own talk
            #   step, `_conduit_listen` will most likely return the peer payload now
            # - INVITE_STATUS_CHANGED: Triggered if the peer reset the invitation or if the
            #   invitation has been deleted, in any case `_conduit_listen` will detect the
            #   listen is not longer possible and raise an exception accordingly
            while True:
                await waiter.wait()
                waiter.clear()
                peer_payload = await self._conduit_listen(listen_ctx)
                if peer_payload is not None:
                    return peer_payload

    async def _conduit_talk(
        self,
        organization_id: OrganizationID,
        greeter: UserID | None,  # None for claimer
        token: InvitationToken,
        state: ConduitState,
        payload: bytes,
    ) -> ConduitListenCtx:
        """
        Raises:
            InvitationNotFoundError
            InvitationAlreadyDeletedError
            InvitationInvalidStateError
        """
        raise NotImplementedError()

    async def _conduit_listen(self, ctx: ConduitListenCtx) -> bytes | None:
        """
        Returns ``None`` is listen is still needed
        Raises:
            InvitationNotFoundError
            InvitationAlreadyDeletedError
            InvitationInvalidStateError
        """
        raise NotImplementedError()

    async def new_for_user(
        self,
        organization_id: OrganizationID,
        greeter_user_id: UserID,
        claimer_email: str,
        created_on: DateTime | None = None,
    ) -> UserInvitation:
        """
        Raise: Nothing
        """
        raise NotImplementedError()

    async def new_for_device(
        self,
        organization_id: OrganizationID,
        greeter_user_id: UserID,
        created_on: DateTime | None = None,
    ) -> DeviceInvitation:
        """
        Raise: Nothing
        """
        raise NotImplementedError()

    async def delete(
        self,
        organization_id: OrganizationID,
        greeter: UserID,
        token: InvitationToken,
        on: DateTime,
        reason: InvitationDeletedReason,
    ) -> None:
        """
        Raises:
            InvitationNotFoundError
            InvitationAlreadyDeletedError
        """
        raise NotImplementedError()

    async def list(self, organization_id: OrganizationID, greeter: UserID) -> List[Invitation]:
        """
        Raises: Nothing
        """
        raise NotImplementedError()

    async def info(self, organization_id: OrganizationID, token: InvitationToken) -> Invitation:
        """
        Raises:
            InvitationNotFoundError
            InvitationAlreadyDeletedError
        """
        raise NotImplementedError()

    async def claimer_joined(
        self, organization_id: OrganizationID, greeter: UserID, token: InvitationToken
    ) -> None:
        """
        Raises: Nothing
        """
        raise NotImplementedError()

    async def claimer_left(
        self, organization_id: OrganizationID, greeter: UserID, token: InvitationToken
    ) -> None:
        """
        Raises: Nothing
        """
        raise NotImplementedError()
