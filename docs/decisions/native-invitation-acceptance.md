# Accepted APBRA-184 technical contract and finite registration

Owner: Haseeb Ul Haque. Acceptance observed18November2026.
Confluence contract: https://arkitektz.atlassian.net/wiki/spaces/APBRA/pages/19398659 version1.
Owner explicitly accepted that reviewed version and the finite9-path registration amendment. The preserved specification below contains its original dated proposed/unmerged wording; that is historical. PR181 is now actually manually merged at 2d7fd0f2121c4bc6a6be6aa70ece317428168c28, with the identical reviewed native tree. This dated acceptance supersedes pending-owner-acceptance wording only; technical semantics and product scope are unchanged.

Registration does not implement invitations, fix dependencies, establish personal acceptance or approve production. Required controls, independent exact-head review, hosted CI, Haseeb manual registration merge and actual-main execution issuance remain prerequisites. No preview/data/settings changes, real provider/email calls, spending, permissions, deployment, automatic approval/merge, Goal or monitoring.

The original docs/source-register.json remains byte-exact with84 historical rows. This stage uses docs/source-register-apbra184.json only for its own new task; original source IDs, versions, statuses, manifests, failures and negative assertions are retained. Source refresh vector119/12/21/IAM10/tenancy8/dataidentity9/identityADR4 is recorded there. The canonical checker ceiling262076bytes is unchanged.

Registration-only scope (exact9):
- docs/decisions/native-invitation-acceptance.md
- docs/source-register-apbra184.json
- scripts/check_bootstrap.py
- scripts/check_nv.py
- scripts/check_recovered_native_registration.py
- scripts/native_invitation_scope.py
- tasks/APBRA-184-native-invitations.json
- tests/bootstrap/test_native_invitation_scope.py
- tests/bootstrap/test_recovered_native_registration_scope.py

Implementation scope is the exact literal path list in the issued task JSON;28 paths for APBRA-184,3 for APBRA-185. No authority accumulates across tasks. The selected base is the actual merged native predecessor; after effective registration, issue a fresh execution record against real main without inventing a future SHA or rewriting frozen historical manifests.

## Preserved reviewed technical specification

# APBRA-184 native colleague invitation contract — proposed v2

Status: technically specified for separate review and owner acceptance; NOT issued implementation authority. No invitation code or candidate has been changed.
Date: 18 November 2026, Australia/Sydney.
Actual author: Codex /root, logical APBRA-ARCH 0.1, through haseebulhaque/id30074430. Human initiator/acceptance authority: Haseeb Ul Haque.
Inspection base: actual main f3e241bbca1358b3cc24738f1a523cadc9a2066f.
Inspection candidate: PR181 edeb26101fb1ad0e9d35871520392e6aa2148047, tree3ae7c67ddaf91c53ff060babf14c617732117440, DRAFT/unmerged.
No future merge revision or implementation head is invented.

## Authority and prerequisites

Owner now selects invitations plus explicit acceptance as the next feature. Current sources:8519682v119,3932362v12 PC26-FR-008,3932382v21,4030847v10 IAM/RBAC,4063408v8 tenancy,4063348v9 identity/audit,3932483v4 identity ADRs. Existing APBRA-151 contract explicitly permits multiple active companies, exact invitation acceptance, independent private grants, no duplicated/reactivated memberships. Existing roles and invitation policy remain controlling.

Implementation requires ALL:
1. Actual Haseeb manual PR181 merge, independently refreshed real main containing the reviewed organisation changes.
2. Acceptance of this native recipient/proof/lifecycle ADR; the explicit new policy recommendation is in DECISIONS.md.
3. A separately reviewed/CI-qualified/manual-merged finite registration/task contract for the exact future source paths. Existing frozen N17 does not authorise them.
4. Fresh actual base/head/actor/PLAN before edits; revalidate source versions, migration head, dependencies and mandatory checks. If main differs, bind the issued contract to actual new base without rewriting historical contracts/manifests.
Product, source registration, implementation, test evidence, personal acceptance and merge remain distinct.

## Roles and boundaries

Current active COMPANY_OWNER and COMPANY_ADMIN may issue/list/revoke native invitations for their selected company. Resolve actor and recheck current active account, native principal, parent-bound workspace session, company and membership under locks. MEMBER and EXPERT cannot invite. Permitted invited roles are exactly existing COMPANY_ADMIN, MEMBER, EXPERT; never COMPANY_OWNER. This does not add role powers: existing owner-only MEMBER↔COMPANY_ADMIN changes and last-owner controls stay unchanged. EXPERT membership is not a private-case grant or review/release approval.

Membership elsewhere does not block a valid target-company invitation. Existing active target membership returns explicit MEMBERSHIP_ALREADY_EXISTS conflict, no consumption, duplicate, role overwrite or privilege upgrade. Existing inactive target membership returns access-unavailable conflict and cannot be reactivated through invitations; route to current authorised owner/operator. No public company discovery, account linking, domain auto-join, fabricated OIDC issuer/subject, SSO, platform console or own-agent setup.

## Recipient binding: an invitation grant plus native account proof

An owner supplies a delivery email and permitted role, never a recipient identity/company/issuer selected by the client. Use the existing normalized_email canonical key, not new alias/domain matching. The email is a delivery address and recipient constraint, never a membership grant.

A native invitation authorises exactly one company/role through an immutable server-issued row, unguessable proof, current eligible issuer, active verified native recipient and explicit acceptance.
- If a native PasswordAccount exists at issue, internally pin its immutable account UUID and epoch. Do not disclose account existence/active state in the issuer response. Never rebind it to a later account with the same address or to an external provider identity.
- If no account is visible at issue, leave recipient UUID unresolved. Normal signup and email verification create the account; no placeholder/unverified account or membership is seeded. On explicit acceptance, require the active, normally verified native account with the exact canonical delivery key and epoch1; then atomically pin its UUID/epoch. Epoch1 means this unresolved invitation cannot survive a recipient password reset after account creation. Conservative conflicts require a fresh owner-issued invitation, not account recovery by linking.
- Account rows exist only after successful normal verification in the current implementation; no client verified flag is accepted. An unresolved invitation requires no created_at ordering assumption: concurrent signup visibility can differ from timestamp order.
- At accept, recheck pinned UUID/epoch, canonical delivery key, active account and native principal. Email changes/account recovery never silently retarget a grant; future email-change support requires a separate contract.
- Create/reuse the explicit account↔native-principal binding under the immutable account lock, preserving NULL external issuer/subject. Creating this principal alone grants no company or private-resource authority.

## Data contract and migration

Proposed Alembic19 file: apps/api/alembic/versions/20261118_19_native_invitations.py, down_revision20261108_18. Verify19 is still free on actual merged main; collision requires a reviewed finite amendment.

Add separate native tables; retain legacy invitations and issuer/subject protocol unchanged:
1. native_invitations: UUID; company_id; issued_by_membership_id + composite company FK; issuer native account UUID/epoch; immutable canonical delivery key/address; nullable intended native account UUID/epoch; existing permitted role; token_digest UNIQUE; expires_at; settings_version_id; created_at; delivery_state; revoked_at/reason; consumed_at/by_account_id/target_membership_id.
2. native_invitation_commands: company/issuer-identity/command-key UNIQUE; canonical payload digest; invitation_id; immutable safe result reference. No raw proof, password or message payload.
3. native_invitation_audit: append-only timestamp, event/outcome enum, support reference, server-derived invitation/company/account/membership IDs where known. Nullable pre-membership actor; no raw proof/digest, password, email body or untrusted exception text.

Use composite FKs for issuer and consumed membership to target company, account FKs to native password accounts and a CHECK on non-owner roles. Consumption fields are all present or all absent; consumed account equals pinned recipient. Business-intent fields cannot mutate after issue; unresolved recipient may transition once to the accepted UUID/epoch. Migration must enforce append-only audit and immutable intent with existing trigger conventions, without deleting retained data. Existing company/account/principal/workspace/legacy IDs and audit remain unchanged.
Downgrade with new retained invitation/audit data fails explicitly; only empty disposable migration fixtures may downgrade. No migration touches the running preview or owner DB.

## HTTP contract

Management uses the existing native workspace cookie, X-CSRF-Token and selected server actor:
- POST /api/native-invitations — email, role, optional expires_in_days plus Idempotency-Key. Company/issuer/recipient UUID fields rejected. Use current tenant invitation_ttl_days (currently seeded7, accepted range1..30), snapshot its settings version; no new TTL/cap.
- GET /api/native-invitations — selected-company management only; keyset page over created_at+id, existing history default50/max100; validated cursor scoped to actor/company/query, no foreign rows. Return safe recipient delivery metadata, role, expiry/lifecycle/delivery state; no token or proof digest.
- POST /api/native-invitations/{id}/revoke — current manager checks; same-company ID only; pending revocation idempotent. Consumed invitation yields explicit already-accepted conflict and route to existing membership management, never removes a member.

Recipient endpoints MUST live under /api/password because the existing password cookie is path-scoped there. They require the existing X-Password-CSRF challenge, current password parent and active account even with NO workspace cookie/principal:
- POST /api/password/invitations/inspect — proof only; authenticated, eligible-recipient safe summary (organisation name, role, expiry), no mutation/consumption/membership. Invalid/foreign/unavailable uses one non-enumerating public response.
- POST /api/password/invitations/accept — proof only; explicit action. Server derives recipient and company/role; no client acceptance/verified flag. Initial success201 returns receipt+membership, binds workspace only to this parent and accepted membership after successful DB commit.
- Exact consumed retry by same account/current epoch with still-active target membership returns200 ALREADY_ACCEPTED, same durable receipt; no second membership/success audit, no role change or automatic switch. The receipt is derived solely from immutable consumed-row fields: id=invitation.id, invitation_id, company_id, membership_id=target_membership_id, role_at_accept=issued role, accepted_at=consumed_at. Initial201 and replay200 return the identical receipt object; only status differs. Consume makes these fields immutable in the DB; no mutable current role or delivery state is part of the receipt. UI offers Open organisation using existing POST /api/password/workspace then /api/auth/select-company with fresh workspace CSRF and the server-returned membership ID. A lost first response therefore has a safe recovery path.
- Evaluate replay after authenticating/locking the current recipient and checking recipient UUID/epoch plus active company/principal/target membership, but BEFORE pending-only issuer/expiry/delivery checks. An already committed receipt remains readable by that eligible current recipient after the original issuer later logs out/resets/loses role or the original invitation expires; this is a receipt, not a new grant. No workspace cookie is minted on replay. A later target-role change never overwrites the membership from role_at_accept. Other-account replay, stale recipient epoch, inactive company/recipient/target membership deny. For UNCONSUMED invitations, revoked/expired/invalid/not-submitted proof or stale/inactive issuer also deny. Existing ordinary sign-in/workspace restore remains available after an accepted member resets their password; the old invitation never reactivates access.
Keep current password-auth peer/proof attempt controls, challenge/Origin/CSRF checks, request bounds and secure cookie settings. Do not invent a separate invitation-volume cap or relax existing limits. No public real-email launch/rate-policy acceptance follows from local capture.

## Delivery and idempotency

Reuse existing secrets.token_urlsafe(48) invitation entropy, SHA256 digest and existing validated proof bounds. Plaintext appears only in process memory and authorised private local capture/transport; never owner JSON response, logs, audit, localStorage/sessionStorage, URL query/path, Git or public artifacts.

Issue atomically commits immutable intent, pending PREPARED/not-acceptable row, issue audit and payload-bound command record. Same key/payload returns the same safe invitation reference; changed payload conflicts. It never returns/reconstructs/resends the secret. Fresh issue after failure is an explicit new command/key; owner can revoke original.

Exactly one after-commit mail submission uses a server-constructed same-origin /invitation#native_invitation=PROOF link. The mail adapter must distinguish invitation purpose from verify/reset. Only after successful submission does a second transaction activate delivery_state=SUBMITTED (not confirmed inbox delivery) plus audit. Failed/uncertain/crashed dispatch stays NOT_ACCEPTABLE even if follow-up failure-audit storage fails; no auto retry. A recipient clicking before activation sees a safe not-ready/retry route, not a falsely expired or accepted grant. A crash after mail but before activation requires fresh owner issuance; no plaintext outbox or guessed resend. Do not hold DB locks during mail I/O.
Revoke-before-activation wins: activation rechecks revoked/consumed/expiry and never resurrects a grant. Local capture proves retrieval only; real SMTP/inbox acceptance is separate.

## Explicit UI journey and invitation precedence

Native User management offers email/role, issue status, current pending list and revoke; native identity details must not call a NULL provider subject an email. Existing membership role/deactivation UI retains its exact permissions.
The /invitation landing captures and immediately scrubs only its dedicated fragment key, validates proof shape and keeps it in component memory. Never autoaccept on GET, sign-in, verification or reload. No proof persistence in browser storage/history. A reload may require reopening the original invitation message, with clear action.
- Existing verified account: open invitation, sign in if necessary, review intended organisation/role, explicitly Accept, enter that workspace.
- New account: create account via normal flow, open separate verification message, verify with signup password, explicitly sign in, reopen original invitation message, review and Accept. The original link remains usable until actual consumption/expiry/revocation. Account verification does not accept it.
- A valid proof-bearing recipient lane is evaluated before generic Create organisation. Email-only discovery must not grant access OR globally block onboarding because another company invited an arbitrary address. Eligibility for this native lane requires the live proof and verified recipient. Invalid/lost proof gives reopen-inbox/request-owner route. An ordinary no-proof account remains ordinary onboarding; no automatic company choice.
- Clear current-company private cases/settings/cache before switching after explicit acceptance. Fresh login with multiple memberships uses existing authorised company selection. No other organisation or its private reports becomes accessible.

The final visible candidate must demonstrate both existing-account and new-account journeys in real browser and private inbox on desktop/320px/keyboard. Provision a NEW isolated invitation preview/database/capture instance after qualification; keep the current58731/18491 preview, inbox, accounts and organisations unchanged and available. Announce its actual tested URL/revision; no silent adoption or copying user demo data. Tests use separate disposable databases.

## Reset, deactivation and issuer authority (new policy recommendation)

Pending acceptance requires issuer account active/current epoch, native identity active, company active and original issuing membership active with current can_invite. Native issuance stores issuer account epoch. Password reset invalidates all its pending proofs by epoch mismatch; ordinary logout/expiry only revokes that session and does not undo the committed invitation. A pending recipient-pinned invitation similarly fails after recipient reset. An unresolved recipient may bind only initial epoch1 as above.
MembershipService deactivation/demotion that removes can_invite must revoke its pending native invitations atomically under the same company lock, with audit; regaining a role cannot revive them. Recipient deactivation blocks acceptance; no invitation can reactivate an inactive account/principal/membership. Any future account reactivation must advance the existing account epoch; reactivation is not implemented by this slice.
After successful acceptance, later issuer reset/deactivation/demotion does not cascade-delete the colleague membership. Future access depends on that colleague's own current account/session/membership/exact resource grants. Recipient reset revokes its parent/derived sessions while preserving accepted membership. Token revocation after consumption is not member deactivation.

## Transaction/lock protocol

Non-locking pre-reads may discover row IDs but never authorise an action. Every predicate/time is re-read after acquiring locks, including after unique-key waits.
Native acceptance/issue lock all involved password account rows in ascending UUID order → the caller password-parent row (multiple parents, if actually needed, sorted by digest) → any existing caller workspace-session row (sorted UUID) → target company → native invitation rows in ascending UUID order → involved principal/identity rows in ascending UUID order → membership/command rows. An issuer pending invitation requires current account/epoch/membership, not its old issuing session. Acceptance locks the recipient current parent and any supplied same-parent workspace; management locks its current native manager parent/workspace. No account/parent/workspace lock may be acquired after a company lock. Read/validate the account/principal/session association after each wait; no touched_at write/autoflush may take a hidden inverse lock. Revalidate preliminary recipient/issuer bindings; changed discovery fails/restarts the command with no partial effect.
Password reset retains existing proof→account→password-session-update flow and never locks company/invitation/principal/workspace rows; monotonic epoch checks invalidate invitations without inverse-lock updates. Native signin rotation uses account→old-parent; native password signout locks parent only and never later waits for account/company/identity, so it can complete before a waiting accept. Native workspace logout and selection must be adjusted in api.py/native_organisation.py to pre-resolve IDs, acquire account→parent→workspace, revalidate, and only then update/revoke/select; no workspace-first→parent inversion. Existing external-provider paths retain their semantics. Password/session reads and native organisation/workspace operations must use the same safe helper/order in the already allowed files; no stale session may authorize an issue/accept after logout wins. If acceptance commits first, subsequent logout revokes access even when a delayed response carries its now-invalid workspace cookie; the membership/audit committed before logout remain historical business state.
Membership mutations retain company-first serialization and acquire pending native invitations before identity/membership locks; they never subsequently lock password accounts. Pre-resolve target IDs without locks, then use the common order and current-state rechecks. Legacy invitation consumption stays company→legacy invitation→identity.
For native creation replay targeting an existing company, pre-resolve the command under account lock and acquire that company BEFORE principal/identity locks. Native no-company creation follows account→parent→existing-workspace ordering, then may lock its principal and insert a NEW company only; it must not then lock a pre-existing company. Extend tests across existing creation retry, acceptance, role/deactivation and reset; a deadlock is a failed required check, not hidden by unlimited retries.
Atomic acceptance covers principal binding, recipient pin, unique membership, proof consumption, receipt and success audits. Any injected DB failure rolls all back, including newly created principal and derived workspace session. No cookie is set until successful commit. Failed-attempt audit is appended in a separate short transaction after rollback using safe server-derived facts; an audit failure cannot turn a denial into a grant.
Revoke versus accept and demote/deactivate versus accept linearise on company/invitation locks. Two proofs for same recipient/company have one membership; the loser conflicts without consumed false-success or role overwrite. Different companies preserve two memberships, with account locking ordered to prevent cross-invite cycles.
Audit must distinguish ISSUED, SUBMISSION_ACCEPTED/FAILED/UNCONFIRMED, REVOKED, ACCEPTED, rejected/expired/epoch-invalid and idempotent receipt. No duplicate successful-accept event on replay. No raw bearer proof/email body in retained evidence.

## Verification and release

APBRA-184-TEST-MATRIX.md defines mandatory positive and negative cases. Full actual future candidate requires API/PostgreSQL/migration/rollback/concurrency/isolation, all web/types/build/bridges/lint, complete browser suite, policy/canonical/full bootstrap, pinned Linux tree+history secret scan, full dependency audit with unresolved findings retained, fresh exact-head review and all required hosted CI. No previous PR181 pass is transferred to changed bytes. New test-only browser app must refuse non-test profiles/non-disposable database/real transport; default production app must not expose captured proofs.

Implementation literal paths and separate registration plan are in the task JSON/REGISTRATION-PLAN.md. Dependencies/.github/provider/owner state remain restricted. Haseeb manually merges; no Done/MVP/production claim or new native permission is made by this specification.


## Preserved reviewed test matrix

# APBRA-184 meaningful test and evidence matrix — proposed v2

No new implementation/test run is claimed. Existing PR181 evidence is historical to the inspected bytes. All following tests must execute against the eventual actual base/head and disposable infrastructure.

| ID | Layer/scenario | Required assertions |
|---|---|---|
| A01 | API owner and admin issue | Current native account/parent/company/member rechecked; non-owner target roles exact; digest-only row, safe response, no membership yet |
| A02 | API Member/Expert/foreign/stale manager | Forbidden; no row, delivery or audit claiming success; forged company/issuer/recipient UUID/owner role rejected |
| A03 | API issue idempotency | Same actor/key/canonical payload one row/dispatch; changed payload conflicts; key isolated across actors/companies |
| A04 | HTTP delivery | PREPARED unusable; successful local capture activates only after safe commit; exception/timeout/crash leaves unacceptably pending; no automatic resend |
| A05 | Race dispatch versus revoke/expiry | Activation cannot resurrect revoked/expired row; no mail under transaction lock |
| A06 | API known recipient | Pinned immutable UUID+epoch; other native/external account with same/display email denied; issuer response does not enumerate existence |
| A07 | API unresolved recipient | No placeholder account; real signup/verification then accept binds exact account; wrong email/epoch>1 requires fresh invite; concurrent account visibility not judged by created_at ordering |
| A08 | API before workspace | Valid password parent without principal/workspace can inspect/accept; normal verification and explicit signin required |
| A09 | HTTP CSRF/cookie | Password routes receive path-scoped cookie; no-session/stale-parent/forged challenge/Origin/cross-account workspace denied |
| A10 | UI explicit action | GET/open/verify/signin/inspect never consumes or joins; summary shows intended company/role before Accept |
| A11 | API malformed/foreign-used/unconsumed-expired/revoked proof | Non-enumerating denial, no raw token echo/company metadata, support reference safe; proof shape and attempt controls unchanged |
| A12 | API active target membership | Explicit conflict, no duplicate/consume/role update; ordinary existing-membership route remains |
| A13 | API inactive target/account/principal/company | Denied, no reactivation; re-signup/new invitation cannot escape inactive state |
| A14 | API other-company membership | Accept exact target in addition; preserve other membership/private cases; no implicit private grants |
| A15 | API same-account consumed retry | Byte-equivalent immutable receipt object/ID/timestamp/role_at_accept; no second success audit/member/role update/cookie/switch; later issuer reset/demotion/original expiry do not undo prior grant; changed target role stays current; recipient reset/inactive target denies replay |
| A16 | API different-account replay | Denied even if token copied; consumed grant never retargeted |
| A17 | Concurrent same proof | One membership, one consumption and one success audit; safe same-account receipt after wait |
| A18 | Concurrent two proofs same company | One unique member; loser conflict/unconsumed, no role overwrite |
| A19 | Concurrent different companies | Preserve both memberships; deterministic account locking, no deadlock/lost binding |
| A20 | Concurrent reverse issuer/recipient | Two accounts invite each other across companies; ascending account locks, no cycle |
| A21 | Issuer demotion/deactivation race | Serial order determines outcome; pending invitations revoked atomically if loss wins; regaining role never revives proof |
| A22 | Issuer reset race | Epoch change before accept denies pending proof; already accepted colleague retains membership; logout alone does not undo committed grant |
| A23 | Recipient reset race | Independent parent+derived sessions positive before reset then denied; pinned/unresolved old invite invalid; fresh invitation/new password may succeed |
| A23b | Accept/issue versus parent signout, native workspace logout, signin rotation and selection | Session-row locks serialize current authority; logout-first denies new grant, accept-first preserves committed business state but later logout makes all old parent/derived cookies unusable; no workspace→parent lock cycle or hidden autoflush inversion |
| A24 | Existing organisation creation retry race | Existing-company replay follows company-before-identity order; no deadlock with native accept or membership management |
| A25 | DB failure injection | Fail after principal insert/member flush/consume/audit before commit; all business state rolls back; denial audit separate/no false success |
| A26 | Commit/lost response | Accepted state+audit durable; receipt retry safe; user can reopen intended current membership without a second grant |
| A27 | Revoke after accept | Explicit already-accepted response; only existing authorised membership-deactivation flow can remove access |
| A28 | Tenant/private isolation | Two normally created organisations/accounts; guessed company/member/invitation IDs denied; same-company colleague cannot read owner’s private case without a grant |
| A29 | List pagination | Stable company-scoped cursor, existing bounds, revoked/expired states truthful; cursor/context switch cannot leak prior company rows |
| A30 | Audit/privacy | Append-only success/denial/delivery/lifecycle records; typed reasons/IDs only; no proof/digest/password/mailbody/raw exception in logs/JSON/trace |
| M01 | Migration18→19 populated fixture | Preserve external and native accounts, identities, memberships, epoch/session/proof history, legacy invitations and exact IDs |
| M02 | Constraints | Composite company/member FKs, role exclusion, unique token/command/membership, coherent consumption fields, one-way recipient binding |
| M03 | Downgrade | Empty own fixture may downgrade; retained invitation/audit data refuses destructive downgrade |
| B01 | Real browser+inbox existing account | Owner issues; colleague opens mail, signs in, explicitly accepts; authoritative target role/company and workspace |
| B02 | Real browser+inbox new account | Owner issues; signup→separate verification→explicit signin→reopen original invite→Accept; no seeded membership/verified flag |
| B03 | Desktop/mobile320/keyboard | Complete B01/B02 with labelled fields, focus, Enter/menu/tab use and no overflow; capture screenshots without raw proofs |
| B04 | Browser reload/logout/return | Current membership retained, multiple-company selection authoritative; other company’s cached private data cleared |
| B05 | Browser rejection/recovery | Wrong account, expired/revoked/used link, inactive membership, not-ready mail, lost-memory/reopen-inbox route actionable |
| B06 | Browser reset acceptance | User personally submits credential change when required by computer-use rules; automation uses normal synthetic endpoint then real new-password signin; evidence labels exact layer |
| H01 | Test-only capture fixture | New browser-app factory refuses non-test profile, wrong DB, real SMTP/provider credentials; default app has no capture endpoint |
| R01 | Full regressions | Complete API, web and browser suites unfiltered; old assertions/hashes/failures retained, no skipped mandatory validation |
| R02 | Engineering/security | Policy/canonical/full bootstrap, lint/types/build/bridges, actual pinned Linux x64 secret tree+nonshallow history and complete npm audit |
| R03 | Source/review/hosted | Clean exact source inventory, independent final base/head review, all4 actual hosted jobs/logs/checkout-tree/nativecheck identity; manual merge |
| P01 | Preview preservation | Current58731/18491 service/data/inbox untouched; future candidate uses a separate tested URL and own DB/capture; no owner config/data inspection |
| U01 | Personal acceptance | Haseeb’s checklist outcomes recorded only when actually reported; neither agent browser checks nor CI are personal acceptance |

Negative fixtures may create narrowly identified inactive/expired states in their OWN disposable database. They must never be described as real invitation acceptance. Happy paths use normal account creation, verification, owner issuance, explicit recipient acceptance and server-created membership only.


End of preserved technical specification. Implementation and release gates remain separate.
