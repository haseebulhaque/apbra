# Isolated Foundry v10 report transport

Haseeb Ul Haque accepted this five-file governance registration for APBRA-160 on 26 November 2026. It reserves a transport and its tests for a separately issued implementation. Protected main at selection was `c0952cfcd30aa4ef05b0d2eb96ddf8374febd9d0`. [Owner selection and PLAN](https://arkitektz.atlassian.net/browse/APBRA-160?focusedCommentId=11130)

## Why the transport needs its own scope

The selected saved prompt agent, version 10, has Code Interpreter. The shared Responses endpoint serves version 7. The released signed-in Generate action sends its request to that shared endpoint without an explicit version. The earlier v9 operator's lease closed, and its receiver lacks the current file-parts argument. Prior synthetic downloads and earlier live v9 files retain their original provenance. [Route qualification](https://arkitektz.atlassian.net/browse/APBRA-160?focusedCommentId=11129)

## Decision

Reserve exactly these two paths:

- `apps/api/src/apbra_api/foundry_v10_report_transport.py`
- `apps/api/tests/test_foundry_v10_report_transport.py`

A future receiver can derive the project Responses route from the server-qualified profile and explicitly name the saved agent and version string `10` in `agent_reference`. Select the already configured Code Interpreter for the confirmed synthetic case. Preserve the stored agent configuration and shared v7 route. Retain the released receiver signature, including image and file parts. Reject unsupported inputs before sending. Include the complete permitted CSV and confirmed requirements. Use one atomic dispatch and zero automatic retries. [Microsoft project Responses API](https://learn.microsoft.com/en-us/rest/api/microsoft-foundry/aiproject#responses)

Qualify the actual service-reported agent and version, successful producing tool call, and service-issued file reference belonging to this operation. Keep an ambiguous file in protected history. APBRA must independently verify the artifact's origin, inspect the unmodified original bytes, record their digest and serve the authenticated case download. A tool attachment, file receipt or matching digest alone leaves report editability and fidelity unverified. [Report acceptance contract](https://arkitektz.atlassian.net/wiki/spaces/APBRA/pages/9404417)

## Release and acceptance

Only the five registered governance files belong in this PR. Preserve the two historical PR197 fixture files at their released bytes, the eight PR198 Markdown files, the two released metadata files and the 28 frozen invitation paths. Prove direct-branch, GitHub merge-checkout and ordinary post-merge behaviour. Verify branch, ancestry, file contents, modes and exact scope. A product proposal touching either reserved path must remain ineligible on both sides of this registration's merge.

Haseeb retains manual merge after separate exact-revision review and passing required CI. Once merged, refresh actual main and issue a separate finite implementation task before product changes. Signed-in receiver integration and operational use require their own qualification, including the current APBRA caller's project and file-read access, case confirmation, current one-use reserve and expiry. Testing approval is recorded. This registration grants no live invocation, spending, permission, deployment or routing authority. Full report acceptance requires an observed v10-generated editable project, an authenticated byte-identical download, a successful Power BI Desktop open and comparison with the confirmed request.
