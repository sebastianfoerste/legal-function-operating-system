# 0005. Presence is held in memory only and is never an audit event

- Status: Accepted
- Date: 2026-10-28
- Answers owner decision 7 in `docs/research/adaptation-plan.md`: in-memory only, chosen
  on 2026-10-28 when F4 was started.

## Context

The rehearsal had two reviewers act on the same revision; the second write was refused
as stale (`supervised-agent/docs/pilot/RETROSPECTIVE.md`, step B20). The retrospective
proposed showing who else has the matter open. Peers do this with a heartbeat:

- Chatwoot keeps last-seen times in a sorted set with a 20-second window (Observed, MIT).
- Langfuse soft-locks a review item for 5 minutes (Observed, MIT).

Two constraints shape it here:

- The actors are simulated local roles. "Selecting an actor is not authentication", so a
  presence badge must not read as proof that a person is there.
- The store and the hash-chained event log are evidence of decisions. Who looked at a
  matter is not a decision, and recording it would be a new kind of personal record that
  the pilot charter does not cover.

## Decision

- `src/pilot/presence.py` holds a `PresenceBoard` in the API process: per matter, each
  reviewer's display name, role, the revision they loaded and when. It is guarded by a
  lock, and its clock is injectable for tests.
- A reviewer is noted when they load a matter or a command returns its view, and when
  their open room checks in (`POST /pilot/api/matters/{id}/presence` with the revision
  they loaded, every 30 seconds). On every note and every read, entries older than 120
  seconds are dropped from all matters, so the board never holds more than the last two
  minutes.
- The review view adds `also_open_by` and `presence_notice`. Each entry gives the
  revision that reviewer loaded and whether it is older than the revision the viewer
  loaded. A check-in also returns the current revision, so the room can tell the viewer
  they are behind.
- The room shows "Also open in the last two minutes (simulated local role, not
  authentication): …". The line carries no clock, so its live region speaks only when who
  is present changes. When a check-in reports a newer revision than the one loaded, a
  warning with a reload button stays pinned in view and names the newest revision.
- Requesters are neither shown presence nor recorded in it. Their check-in is refused.
- Nothing is written to SQLite, the event log, history, exports or delivery manifests,
  and nothing survives a restart. A test compares a full SQL dump of the store and the
  matter history before and after presence activity, including refused check-ins.

## Consequences

- Reviewers get a warning before they write to a revision someone else has moved on,
  instead of only after the stale refusal.
- Presence is a hint, not a lock and not evidence. It can be wrong: a closed tab stays
  "open" for up to two minutes, and anyone choosing a role appears under that role's name.
- Real presence for named people waits on authentication (owner decision 1); the label
  stays until then.
