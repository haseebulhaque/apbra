# Deployment and handover standards

Version: 1.0.0 | Synthetic customer: Contoso Sales Demo

## Handover evidence
Document local synthetic inputs, model assumptions, validation outcomes, and unresolved deployment actions. Use `TARGET_WORKSPACE_PLACEHOLDER`; never place a real tenant, credential, endpoint, or customer dataset in generated demo artefacts.

The handover should identify the report owner, data refresh assumptions, supported feature boundary, source revision, and required Desktop verification. Generated source, validation evidence, and runtime screenshots are different evidence types and should not be presented as interchangeable.

## Supported feature boundary
The Capstone supports embedded synthetic data, a simple star schema, standard visuals, slicers, and source validation. Production publishing, tenant deployment, enterprise identity, custom visuals, and an operational reviewer workflow are outside this prototype.

Unsupported features must remain visible as warnings or review requirements. The compiler must not replace them with superficially similar features. A Report Design can be complete while generation is withheld because its required capability is unavailable.

## Validation and release
Validate project structure, report-to-model references, table and relationship bindings, measure references, visual definitions, generated identifiers, and package completeness before download. A source-validation pass does not establish Desktop rendering, calculation correctness, refresh success, accessibility, or tenant deployment readiness.

## Data and credential handling
Use synthetic inputs for the Capstone. Do not persist uploaded business files beyond the local browser run, send unnecessary complete datasets to the model, or include provider secrets in browser responses, traces, downloads, logs, or source control. Production requires approved retention, encryption, and tenant isolation controls.
