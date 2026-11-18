# Accepted APBRA-185 technical contract and finite registration

Owner: Haseeb Ul Haque. Acceptance observed18November2026.
Confluence contract: https://arkitektz.atlassian.net/wiki/spaces/APBRA/pages/19496962 version1.
Owner explicitly accepted that reviewed version and the finite9-path registration amendment. The preserved specification below contains its original dated proposed/unmerged wording; that is historical. PR181 is now actually manually merged at 2d7fd0f2121c4bc6a6be6aa70ece317428168c28, with the identical reviewed native tree. This dated acceptance supersedes pending-owner-acceptance wording only; technical semantics and product scope are unchanged.

Registration does not implement invitations, fix dependencies, establish personal acceptance or approve production. Required controls, independent exact-head review, hosted CI, Haseeb manual registration merge and actual-main execution issuance remain prerequisites. No preview/data/settings changes, real provider/email calls, spending, permissions, deployment, automatic approval/merge, Goal or monitoring.

The original docs/source-register.json remains byte-exact with84 historical rows. This stage uses docs/source-register-apbra185.json only for its own new task; original source IDs, versions, statuses, manifests, failures and negative assertions are retained. Source refresh vector119/12/21/IAM10/tenancy8/dataidentity9/identityADR4 is recorded there. The canonical checker ceiling262076bytes is unchanged.

Registration-only scope (exact9):
- docs/decisions/development-dependency-maintenance.md
- docs/source-register-apbra185.json
- scripts/check_bootstrap.py
- scripts/check_nv.py
- scripts/check_recovered_native_registration.py
- scripts/dependency_maintenance_scope.py
- tasks/APBRA-185-development-dependency-maintenance.json
- tests/bootstrap/test_dependency_maintenance_scope.py
- tests/bootstrap/test_recovered_native_registration_scope.py

Implementation scope is the exact literal path list in the issued task JSON;28 paths for APBRA-184,3 for APBRA-185. No authority accumulates across tasks. The selected base is the actual merged native predecessor; after effective registration, issue a fresh execution record against real main without inventing a future SHA or rewriting frozen historical manifests.

## Preserved reviewed technical specification

# APBRA-185 finite dependency maintenance contract — proposed v1

Status: concrete recommendation/finite scope for independent review and owner acceptance. No package, lock, runtime or preview edit has occurred. This contract does not waive an advisory.
Actual actor Codex /root (logical APBRA-SEC0.1) through haseebulhaque/id30074430; initiated by Haseeb Ul Haque. Date18November2026 Australia/Sydney.
Inspection mainf3e241bbca1358b3cc24738f1a523cadc9a2066f / PR181headedeb26101fb1ad0e9d35871520392e6aa2148047. PR181 remains draft/unmerged. Proposed execution branch is separate; no future head/merge SHA is invented.

## Refreshed evidence and inheritance

Fresh isolated full official-registry audit again exits1 with8 affected-package entries:6high,1moderate,1low. Several high entries propagate the same picomatch advisory; these are not8distinct CVEs. Full SHA58cdea41d1964453a5b37620ddfb354a5942b57bbb098907248f6d7e3f579bcd.
Separate production-only comparison exits0/0findings, SHA7b77028cc5a419272393d503fc138172f5b56203dd91b211da1b7ca353f79b09. It does not replace the full audit or establish runtime safety.
Both files independently byte-equal actual main and PR181:
package.json SHA1e446f63b1ef99270d840be1411846dbce57e54b9122282d575d76ed149b994c.
package-lock.json SHAb5b0ba486b57cf077fefc294ebfb0e9edaffc2b98983008885de686388b9244b.
Therefore these findings are inherited, not introduced by PR181. No owner configuration, tokens, inbox data or demo database was read.

Official public registry metadata confirms candidate versions, dependency/peer/engine ranges and MIT/BSD3 licences. Public metadata was fetched unauthenticated, no package downloaded/installed/executed. Current actual local Node24.21.0/npm11.19.0; repository packageManager remains npm11.6.0. Future lock generation must use the existing declared npm11.6.0 and a supported existing Node24 profile; do not silently change packageManager/Node engines. Existing CI observed Node24.19.0; verify its actual tool versions again during qualification.

## Package-by-package recommendation

| Affected locked node / dependency path | Exposure in this repository | Proposed fix or bounded mitigation | Remaining uncertainty / validation |
|---|---|---|---|
| vite7.3.6; direct dev, also vitest→vite | Five launch-editor/custom-HTML/file-system advisories; Vite runs in actual E2E. Persistent stakeholder preview is Python+static assets. Loopback alone is not a universal mitigation. | Pin direct vite7.3.8; primary advisories list7.3.7 fixes and the7.3.8 official release/registry exists. Retain7major. | Compatible engine^20.19 or>=22.12 and Vitest peer range include observed Node24/Vite7. Full actual build/E2E/proxy/adapter regression still required. The picomatch transitive risk remains. |
| vitest4.1.11; direct dev | Highest severity includes inherited glob risk and @vitest/mocker issues; ordinary vitest run src, not a public mocker server. | Pin vitest4.1.12; keep its exact @vitest family coherent via generated lock. | Release backports mock hardening; supported Node^20/^22/>=24 and Vite6/7/8 include current24/7.3.8. Full631+future web tests must actually run; no claim old tests qualify changed tooling. Glob chain may remain. |
| @vitest/mocker4.1.11 via vitest | Manual WebSocket mock-registration injection and Windows redirect traversal prerequisites; public mocker/interceptor plugin not registered in current Vite config. | Resolve4.1.12 through vitest4.1.12, not a new direct dependency/override. | Confirm actual installed mocker/family4.1.12 in lock and runtime; no native browser/server plugin exposure. Mac/Linux tests do not establish Windows runtime qualification. |
| esbuild0.27.7; direct dev and vite→esbuild | Advisory concerns Windows development server; repository uses fixed CLI builds for web and semantic/generation bridges, not esbuild serve. | Pin esbuild0.28.2; official fix starts0.28.1 and0.28.2 exists. Vite7.3.8 accepts^0.27.0 or^0.28.0. | 0.x minor is a compatibility boundary, not an automatic safe patch. Verify both bridge builds/imports and complete API/compiler/output semantic regressions, not merely npm install. No Windows PASS claimed. |
| source-map-js1.2.1 via vite→postcss8.5.28→source-map-js | Indexed-source-map offset DoS on malicious map input. Current native account forms are not a map ingestion API; build inputs still require trust. | Resolve transitive1.2.2 within PostCSS’s existing compatible range; no new top-level runtime dependency. | Confirm every resolved copy and actual parent range. Build/CSS/source-map processing must pass. Do not use an override that hides an incompatible parent. |
| picomatch4.0.7 via vite/vitest/tinyglobby/fdir | Crafted attacker-controlled glob patterns can block Node’s event loop. No new native-flow sink identified; build/test/repository inputs remain a development risk. | No patched registry release: latest is4.0.7 and GHSA lists none. Retain visible finding under the proposed restricted trusted-build/static-preview profile below, pending explicit owner decision; no fork/vendor/unreleased-commit pin or replacement selected. | Upstream PR194 is OPEN, concerns leading-question-mark extglob parsing and is not a released resolution of this repeated-extglob advisory. Parent fixAvailable is not remediation. Exact residual post-update audit count must be measured. |
| fdir6.5.0 via vite/tinyglobby, optional picomatch peer^3or^4 | Propagated picomatch finding, not an independent native runtime defect. | Keep current compatible6.5.0 (official latest); resolve parents only as required for selected fixes, do not add/replace crawler. Apply same trusted-input residual controls. | Merely bumping Vitest cannot remove an unpatched peer issue. Verify installed graph/full audit and reachable glob inputs. |
| tinyglobby0.2.17 via vite/vitest; deps fdir^6.5 and picomatch^4.0.4 | Propagated unpatched glob risk in build/test discovery. | Retain compatible0.2.17 (official latest) unless reviewed minimal resolution needs otherwise; same residual controls, no unsupported replacement. | Current range still permits affected4.0.7; full audit remains authoritative. No zero-finding prediction. |

All8 entries are dev:true in current lock. This classification is an input to exposure analysis, not proof of harmlessness. Built static assets and compiled Node bridges must be assessed by actual imports/entrypoints; string search or tree-shaking assumptions alone are insufficient.

## Precise residual-picomatch mitigation proposal requiring owner acceptance

Recommend AVAILABLE FIXES PLUS RESTRICTED DEVELOPMENT PROFILE:
- Stakeholder previews use already-built static assets behind the normal Python API; never expose Vite/Vitest/esbuild development-server handlers as the preview service.
- Native/account/upload/business text cannot become a glob pattern, build option, source-map input, shell command or repository configuration. Existing scripts use fixed reviewed TypeScript entrypoints and fixed test-source paths; verify this boundary and reject arbitrary compiler/configuration inputs through application routes.
- Build/test only reviewed trusted source/configuration/dependencies. Untrusted PR/repository/fixture input runs only in existing disposable isolated public CI with read-only token/no owner credentials/production data, not the user’s working preview or private environment. Do not call bootstrap tests an isolation sandbox.
- Keep development/test servers confined to their existing disposable synthetic profile and loopback, while recognising loopback by itself does not remove the documented browser/dev-server risks. Do not broaden network exposure or register public mocker/custom-HTML integrations.
- Keep the FULL audit finding, raw original output, advisory/version evidence and APBRA-185 obligation visible. Recheck upstream at a later selected maintenance execution; this chat enables no monitoring/automation.
- Any request for untrusted glob/config/source-map input or wider development-server exposure fails closed pending a separately accepted mitigation/fix. No new numeric length/CPU/rate ceiling is invented as a substitute.
- The scope owner must explicitly accept that this profile retains an unresolved development dependency risk. It does not mark the audit PASS or approve production/external exposure. If the owner declines, hold maintenance acceptance for an actual upstream patch or a separately selected supported alternative; available fixes can remain a reviewed proposal.

This is a specific operational/input-boundary proposal, not a newly implemented runtime sandbox. Where controls are documentary/existing they must be labelled so; future validation cannot claim universal nonreachability or exploit-proof operation.

## Finite changed paths and patch procedure

Exactly3 proposed implementation paths:
1. apps/web/package.json — only selected exact Vite/Vitest/esbuild dev pins; preserve all prod dependencies, scripts, engines and packageManager unless an accepted amendment is required.
2. apps/web/package-lock.json — minimal coherent resolution for those pins, source-map-js1.2.2 and necessary version-family/platform binaries. Review every changed node/URL/integrity/engine/peer; reject unrelated churn.
3. docs/engineering/development-dependency-security.md — actual exposure/versions/full residual findings/profile/owner decision and evidence, explicitly distinguished from implementation.

No code, feature, API migration, Vite adapter/proxy, Playwright configuration, test assertion, workflow, original source manifest or current preview change is authorised.
Planned commands ONLY after accepted effective contract/registration: use declared npm11.6.0 to create a package-lock-only/ignore-scripts resolution for exact vite7.3.8,vitest4.1.12,esbuild0.28.2; targeted transitive source-map-js update within its verified parent range. Then inspect diff and execute clean locked install in disposable qualification workspace. These commands have NOT run. Do not run npm audit fix/--force, broad npm update, suppressions or unsupported replacements. If compatibility requires an extra application/test/config path, stop for a reviewed finite amendment instead of weakening tests.

Separate registration proposal and3path Task Contract are in REGISTRATION-PLAN.md and APBRA-185-TASK-CONTRACT.proposed.json. Recommend execution on verified actual main after manual PR181 merge so its frozen candidate is not rebased or replaced. Any later source change must get new exact-head evidence; none of current PR181 passes transfers.

## Mandatory acceptance and validation

- Fresh baseline and candidate package graph/full audit comparison; retain full audit exit1 for residual findings and separately classify newly introduced/removed/persisting entries. Production-only comparison is additional, never replacement. No known fixed advisory may remain through an unintended nested vulnerable copy.
- Official version/license/engine/peer evidence; actual declared-package-manager lock generation; clean frozen npm install; dependency probes for exact selected versions and all changed copies.
- Both semantic and generation bridge builds, Node imports/normal fixture calls, complete API/compiler/PBIP/output regression tests and full Postgres migration/isolation tests. No API migration/code change is proposed, but actual integrated regression remains necessary.
- Full web/unit/types/build and complete browser suite, protected proxy/adapter/account/org/session/private-resource routes. Existing live-provider opt-ins remain explicitly NOT_RUN; no real provider credentials/calls.
- Full CI policy/canonical/bootstrap, exact changed-path inventory/working-source hashes and Linux pinned secret scan of tracked tree/nonshallow fetched history; all required hosted jobs on exact actual base/head.
- Independently reviewed source/graph/advisory/compatibility results and residual-risk disposition, followed by Haseeb manual merge. A meaningful security result includes unresolved findings; CI green is not a clean audit.
- Current macOS/Linux profiles are tested; Windows runtime security is NOT_RUN/not claimed. No new runner, paid tooling or platform entitlement is selected.

No application test/build/migration/browser/scan/hosted run for a changed maintenance candidate is claimed now. Preparation validation is JSON/path/schema/source/advisory review only.

## Primary sources refreshed on18November2026

Official metadata: sources/npm-official-metadata.json includes exact https://registry.npmjs.org package/version URLs, licences, engines and dependencies; audit/full.json retains every GHSA and affected range.
- Vite release https://github.com/vitejs/vite/releases/tag/v7.3.8 ; its five exact advisory links in audit.
- Vitest backport https://github.com/vitest-dev/vitest/releases/tag/v4.1.12 ; https://github.com/advisories/GHSA-qxg6-89mg-rqv8 ; https://github.com/advisories/GHSA-xp26-3454-mjgp
- esbuild https://github.com/evanw/esbuild/releases/tag/v0.28.2 ; https://github.com/advisories/GHSA-g7r4-m6w7-qqqr
- source-map-js https://github.com/7rulnik/source-map-js/releases/tag/v1.2.2 ; https://github.com/advisories/GHSA-68fv-2mgg-jv7q
- picomatch https://github.com/advisories/GHSA-fc5q-39xc-vjpf ; https://github.com/micromatch/picomatch/pull/194

Versions are registry-confirmed options recommended for the future finite patch, not compatibility results or already changed pins. Existing open-source MIT/BSD3 tooling needs no new paid service; standard existing public Ubuntu CI is retained. No cost, provider, region, permission or visibility change.


## Accepted residual-risk decision

The owner explicitly accepted the restricted trusted-development/static-preview profile for bounded local MVP work. Unresolved picomatch development risk stays OPEN. This is not a clean audit, production approval, suppression permission or broader external-development-server exposure. Authorised proposed fixes remain Vite7.3.8, alignedVitest/mocker4.1.12,esbuild0.28.2,source-map-js1.2.2 subject fresh official-source/actual compatibility verification; declarednpm11.6.0 is unchanged.

End of preserved technical specification. Implementation and release gates remain separate.
