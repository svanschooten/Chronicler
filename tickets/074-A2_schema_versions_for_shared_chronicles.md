# 074-A2_schema_versions_for_shared_chronicles

## A chronicle opened by a newer Chronicler cannot be opened by an older one

### info

| | |
| --- | --- |
| importance | medium |
| danger level | Medium: sharing a chronicle, which the README promotes, silently locks out anyone on an older version. Change risk: low for the message, medium for any compatibility rule. |
| reach | Anyone sharing chronicles or a synced workspace across versions |
| effort | S, after the decision |
| evidence | reproduced |
| touches | `chronicler/core/database_manager.py`, `chronicler/core/services/chronicle_service.py`, `docs/storage.md`, `docs/troubleshooting.md`, `README.md` |

### description

Found in the review after wave 4. This is an architecture decision first.

`_project_engine` (`database_manager.py:137-173`) runs the project chain to head the
first time a chronicle is opened, so a database moves to the newest schema in place,
without asking. An older Chronicler then refuses it: a `project.db` stamped with a
revision it does not know fails with `CommandError: Can't locate revision identified by
'…'`, which reaches the user as a generic error.

So a chronicle shared through Dropbox, a network share, a zip export or *Link* works
until someone on a newer version opens it, and from then on it is unreadable for anyone
who has not upgraded. Nothing warns before the upgrade, and nothing documents it. Every
project migration does this, so 063's FTS migration would too.

The same applies to the workspace database, but a workspace belongs to one machine at a
time, so it matters less there.

### proposed fix

Decide the rule, then implement it:

1. **Minimum:** before migrating, compare the database's revision with the chain. If it
   is unknown, raise a clear error ("made by a newer Chronicler, update to open it")
   instead of the Alembic one, and document that opening a chronicle upgrades it.
2. **Better for sharing:** keep project migrations additive, so an older version can read
   a newer file it does not fully understand. Store the oldest app version that can still
   open each revision, and refuse only below that.
3. Consider asking before upgrading a linked chronicle, since its file may be shared.

Done when the decision is written in `docs/storage.md`, and an older version opening a
newer chronicle shows a message that says what to do.

### related tickets

- (BLOCKS) [063-F1_full_text_search](063-F1_full_text_search.md): adds a project migration, so the rule should exist first
- (RELATED) [072-M13_failed_link_leaves_chronicle](072-M13_failed_link_leaves_chronicle.md): linking a newer file is one of the failures it reports
- (RELATED) [061-D3_version_and_status](061-D3_version_and_status.md): the version a minimum would be expressed in
