// Parsec Cloud (https://parsec.cloud) Copyright (c) BUSL-1.1 2016-present Scille SAS

// `allow-unwrap-in-test` don't behave as expected, see:
// https://github.com/rust-lang/rust-clippy/issues/11119
#![allow(clippy::unwrap_used)]

use libparsec_tests_lite::prelude::*;
use libparsec_types::prelude::*;

use super::authenticated_cmds;

// Request

pub fn req() {
    // Generated from Python implementation (Parsec v2.6.0+dev)
    // Content:
    //   cmd: "events_listen"
    //   wait: false
    let raw = hex!("82a3636d64ad6576656e74735f6c697374656ea477616974c2");

    let req = authenticated_cmds::events_listen::Req { wait: false };

    let expected = authenticated_cmds::AnyCmdReq::EventsListen(req);

    let data = authenticated_cmds::AnyCmdReq::load(&raw).unwrap();

    p_assert_eq!(data, expected);

    // Also test serialization round trip
    let authenticated_cmds::AnyCmdReq::EventsListen(req2) = data else {
        unreachable!();
    };

    let raw2 = req2.dump().unwrap();

    let data2 = authenticated_cmds::AnyCmdReq::load(&raw2).unwrap();

    p_assert_eq!(data2, expected);
}

// Responses

pub fn rep_ok() {
    let raw_expected = [
        (
            // Generated from Python implementation (Parsec v2.6.0+dev)
            // Content:
            //   event: "pinged"
            //   ping: "foobar"
            //   status: "ok"
            &hex!("83a56576656e74a670696e676564a470696e67a6666f6f626172a6737461747573a26f6b")[..],
            authenticated_cmds::events_listen::Rep::Ok(
                authenticated_cmds::events_listen::APIEvent::Pinged {
                    ping: "foobar".to_owned(),
                },
            ),
        ),
        (
            // Generated from Python implementation (Parsec v2.6.0+dev)
            // Content:
            //   event: "message.received"
            //   index: 0
            //   status: "ok"
            &hex!(
                "83a56576656e74b06d6573736167652e7265636569766564a5696e64657800a67374617475"
                "73a26f6b"
            )[..],
            authenticated_cmds::events_listen::Rep::Ok(
                authenticated_cmds::events_listen::APIEvent::MessageReceived { index: 0 },
            ),
        ),
        (
            // Generated from Python implementation (Parsec v2.6.0+dev)
            // Content:
            //   event: "invite.status_changed"
            //   invitation_status: "IDLE"
            //   status: "ok"
            //   token: ext(2, hex!("d864b93ded264aae9ae583fd3d40c45a"))
            &hex!(
                "84a56576656e74b5696e766974652e7374617475735f6368616e676564b1696e7669746174"
                "696f6e5f737461747573a449444c45a6737461747573a26f6ba5746f6b656ed802d864b93d"
                "ed264aae9ae583fd3d40c45a"
            )[..],
            authenticated_cmds::events_listen::Rep::Ok(
                authenticated_cmds::events_listen::APIEvent::InviteStatusChanged {
                    invitation_status: InvitationStatus::Idle,
                    token: InvitationToken::from_hex("d864b93ded264aae9ae583fd3d40c45a").unwrap(),
                },
            ),
        ),
        (
            // Generated from Python implementation (Parsec v2.6.0+dev)
            // Content:
            //   encryption_revision: 0
            //   event: "realm.maintenance_finished"
            //   realm_id: ext(2, hex!("1d3353157d7d4e95ad2fdea7b3bd19c5"))
            //   status: "ok"
            &hex!(
                "84b3656e6372797074696f6e5f7265766973696f6e00a56576656e74ba7265616c6d2e6d61"
                "696e74656e616e63655f66696e6973686564a87265616c6d5f6964d8021d3353157d7d4e95"
                "ad2fdea7b3bd19c5a6737461747573a26f6b"
            )[..],
            authenticated_cmds::events_listen::Rep::Ok(
                authenticated_cmds::events_listen::APIEvent::RealmMaintenanceFinished {
                    realm_id: VlobID::from_hex("1d3353157d7d4e95ad2fdea7b3bd19c5").unwrap(),
                    encryption_revision: 0,
                },
            ),
        ),
        (
            // Generated from Python implementation (Parsec v2.6.0+dev)
            // Content:
            //   encryption_revision: 0
            //   event: "realm.maintenance_started"
            //   realm_id: ext(2, hex!("1d3353157d7d4e95ad2fdea7b3bd19c5"))
            //   status: "ok"
            &hex!(
                "84b3656e6372797074696f6e5f7265766973696f6e00a56576656e74b97265616c6d2e6d61"
                "696e74656e616e63655f73746172746564a87265616c6d5f6964d8021d3353157d7d4e95ad"
                "2fdea7b3bd19c5a6737461747573a26f6b"
            )[..],
            authenticated_cmds::events_listen::Rep::Ok(
                authenticated_cmds::events_listen::APIEvent::RealmMaintenanceStarted {
                    realm_id: VlobID::from_hex("1d3353157d7d4e95ad2fdea7b3bd19c5").unwrap(),
                    encryption_revision: 0,
                },
            ),
        ),
        (
            // Generated from Python implementation (Parsec v2.6.0+dev)
            // Content:
            //   checkpoint: 0
            //   event: "realm.vlobs_updated"
            //   realm_id: ext(2, hex!("1d3353157d7d4e95ad2fdea7b3bd19c5"))
            //   src_id: ext(2, hex!("2b5f314728134a12863da1ce49c112f6"))
            //   src_version: 0
            //   status: "ok"
            &hex!(
                "86aa636865636b706f696e7400a56576656e74b37265616c6d2e766c6f62735f7570646174"
                "6564a87265616c6d5f6964d8021d3353157d7d4e95ad2fdea7b3bd19c5a67372635f6964d8"
                "022b5f314728134a12863da1ce49c112f6ab7372635f76657273696f6e00a6737461747573"
                "a26f6b"
            )[..],
            authenticated_cmds::events_listen::Rep::Ok(
                authenticated_cmds::events_listen::APIEvent::RealmVlobsUpdated {
                    realm_id: VlobID::from_hex("1d3353157d7d4e95ad2fdea7b3bd19c5").unwrap(),
                    checkpoint: 0,
                    src_id: VlobID::from_hex("2b5f314728134a12863da1ce49c112f6").unwrap(),
                    src_version: 0,
                },
            ),
        ),
        (
            // Generated from Rust implementation (Parsec v2.12.1+dev)
            // Content:
            //   event: "realm.roles_updated"
            //   realm_id: ext(2, hex!("1d3353157d7d4e95ad2fdea7b3bd19c5"))
            //   role: None
            //   status: "ok"
            //
            &hex!(
                "84a6737461747573a26f6ba56576656e74b37265616c6d2e726f6c65735f75706461746564"
                "a87265616c6d5f6964d8021d3353157d7d4e95ad2fdea7b3bd19c5a4726f6c65c0"
            )[..],
            authenticated_cmds::events_listen::Rep::Ok(
                authenticated_cmds::events_listen::APIEvent::RealmRolesUpdated {
                    realm_id: VlobID::from_hex("1d3353157d7d4e95ad2fdea7b3bd19c5").unwrap(),
                    role: None,
                },
            ),
        ),
        (
            // Generated from Python implementation (Parsec v2.6.0+dev)
            // Content:
            //   event: "realm.roles_updated"
            //   realm_id: ext(2, hex!("1d3353157d7d4e95ad2fdea7b3bd19c5"))
            //   role: "OWNER"
            //   status: "ok"
            &hex!(
                "84a56576656e74b37265616c6d2e726f6c65735f75706461746564a87265616c6d5f6964d8"
                "021d3353157d7d4e95ad2fdea7b3bd19c5a4726f6c65a54f574e4552a6737461747573a26f"
                "6b"
            )[..],
            authenticated_cmds::events_listen::Rep::Ok(
                authenticated_cmds::events_listen::APIEvent::RealmRolesUpdated {
                    realm_id: VlobID::from_hex("1d3353157d7d4e95ad2fdea7b3bd19c5").unwrap(),
                    role: Some(RealmRole::Owner),
                },
            ),
        ),
    ];

    for (raw, expected) in raw_expected {
        let data = authenticated_cmds::events_listen::Rep::load(raw).unwrap();

        p_assert_eq!(data, expected);

        // Also test serialization round trip
        let raw2 = data.dump().unwrap();

        let data2 = authenticated_cmds::events_listen::Rep::load(&raw2).unwrap();

        p_assert_eq!(data2, expected);
    }
}

pub fn rep_cancelled() {
    let raw_expected = [
        (
            // Generated from Rust implementation (Parsec v2.12.1+dev)
            // Content:
            //   reason: None
            //   status: "cancelled"
            //
            &hex!("82a6737461747573a963616e63656c6c6564a6726561736f6ec0")[..],
            authenticated_cmds::events_listen::Rep::Cancelled { reason: None },
        ),
        (
            // Generated from Python implementation (Parsec v2.6.0+dev)
            // Content:
            //   reason: "foobar"
            //   status: "cancelled"
            &hex!("82a6726561736f6ea6666f6f626172a6737461747573a963616e63656c6c6564")[..],
            authenticated_cmds::events_listen::Rep::Cancelled {
                reason: Some("foobar".to_owned()),
            },
        ),
    ];

    for (raw, expected) in raw_expected {
        let data = authenticated_cmds::events_listen::Rep::load(raw).unwrap();

        p_assert_eq!(data, expected);

        // Also test serialization round trip
        let raw2 = data.dump().unwrap();

        let data2 = authenticated_cmds::events_listen::Rep::load(&raw2).unwrap();

        p_assert_eq!(data2, expected);
    }
}

pub fn rep_no_events() {
    // Generated from Python implementation (Parsec v2.6.0+dev)
    // Content:
    //   status: "no_events"
    let raw = hex!("81a6737461747573a96e6f5f6576656e7473");

    let expected = authenticated_cmds::events_listen::Rep::NoEvents;

    let data = authenticated_cmds::events_listen::Rep::load(&raw).unwrap();

    p_assert_eq!(data, expected);

    // Also test serialization round trip
    let raw2 = data.dump().unwrap();

    let data2 = authenticated_cmds::events_listen::Rep::load(&raw2).unwrap();

    p_assert_eq!(data2, expected);
}
