import request from '../../../tests/bootstrap/fixtures/sales-v1/request.json';
import schema from '../../../tests/bootstrap/fixtures/sales-v1/schema.json';
import type {Answers} from './workflow';

// Supported bindings are implementation declarations; expected fixtures are test assertions only.
const supportedRequirements = {
  "fixture_version": "1.0.0",
  "request_id": "sales-request-v1",
  "schema_id": "sales-star-v1",
  "confirmed_clarification_ids": [
    "sales-definition",
    "yoy-coverage",
    "region-security"
  ],
  "sales_definition": "net SalesAmount",
  "currency": "AUD",
  "comparison": {
    "current_year": 2025,
    "prior_year": 2024,
    "missing_or_zero_prior": "blank"
  },
  "region_usage": "slicer_only",
  "rls_required": false,
  "required_measure_ids": [
    "total-sales",
    "total-orders",
    "average-order-value",
    "sales-previous-year",
    "sales-yoy-change",
    "sales-yoy-percent"
  ],
  "pages": [
    "Executive Summary",
    "Regional Performance"
  ],
  "filters": [
    "DimRegion.RegionName",
    "DimBusinessArea.BusinessAreaName",
    "DimProduct.ProductCategory"
  ],
  "time_axis": "DimDate.YearMonth"
};

export type Submission = {original_request: string; original_schema: typeof schema; answers: Answers};
export type RequirementsSnapshot = {
  artifact_kind: 'RequirementsSnapshot';
  version: 1;
  processing: 'DETERMINISTIC_GOLDEN_FIXTURE';
  source: {fixture_version: string; request_id: string; schema_id: string};
  submission: Submission;
  confirmation: 'EXPLICIT_LOCAL_USER_CONFIRMATION';
  requirements: typeof supportedRequirements;
};
export type Assessment = {status: 'AWAITING_CLARIFICATION' | 'UNSUPPORTED' | 'READY_TO_CONFIRM'; issues: string[]};

type SchemaShape = {
  tables: Array<{name: string; columns: Array<{name: string; type: string; nullable: boolean}>}>;
  relationships: Array<{
    from_table: string;
    from_column: string;
    to_table: string;
    to_column: string;
    cardinality: string;
    filter_direction: string;
    active: boolean;
  }>;
};

function ambiguousFactDateRelationship(inputSchema: typeof schema): string | undefined {
  const candidate = structuredClone(inputSchema) as unknown as SchemaShape;
  const baseline = schema as unknown as SchemaShape;
  const candidateFact = candidate.tables.find(table => table.name === 'FactSales');
  const baselineFact = baseline.tables.find(table => table.name === 'FactSales');
  const baselineDateRelationship = baseline.relationships.find(relationship =>
    relationship.from_table === 'FactSales' && relationship.to_table === 'DimDate' && relationship.to_column === 'Date');
  if (!candidateFact || !baselineFact || !baselineDateRelationship) return undefined;

  const baselineColumnNames = new Set(baselineFact.columns.map(column => column.name));
  const addedDateColumns = candidateFact.columns.filter(column =>
    !baselineColumnNames.has(column.name) && column.type === 'date');
  if (addedDateColumns.length !== 1) return undefined;

  const addedColumn = addedDateColumns[0];
  const addedRelationships = candidate.relationships
    .map((relationship, index) => ({relationship, index}))
    .filter(({relationship}) => relationship.from_column === addedColumn.name
      && Object.entries(baselineDateRelationship).every(([key, value]) =>
        key === 'from_column' || relationship[key as keyof typeof relationship] === value));
  if (addedRelationships.length !== 1) return undefined;

  candidateFact.columns.splice(candidateFact.columns.indexOf(addedColumn), 1);
  candidate.relationships.splice(addedRelationships[0].index, 1);
  if (JSON.stringify(candidate) !== JSON.stringify(schema)) return undefined;

  return `Which FactSales date relationship should drive time intelligence: ${baselineDateRelationship.from_column} or ${addedColumn.name}?`;
}

// Exact fixture matching is intentional: arbitrary prose must never inherit golden semantics.
export function assessRequirements(input: Submission): Assessment {
  const issues: string[] = [];
  if (input.original_request !== request.original_text) issues.push('Only the unchanged APBRA-90 request is supported. Edited requests require separate interpretation.');
  const dateRelationshipQuestion = ambiguousFactDateRelationship(input.original_schema);
  if (JSON.stringify(input.original_schema) !== JSON.stringify(schema) && !dateRelationshipQuestion) issues.push('Only the complete APBRA-90 schema and 2024–2025 coverage are supported.');
  const ids = request.clarifications.map(c => c.id);
  if (Object.keys(input.answers).some(id => !ids.includes(id))) issues.push('Unknown clarification answers are unsupported.');
  for (const c of request.clarifications) {
    if (input.answers[c.id]?.trim() && input.answers[c.id] !== c.golden_answer) issues.push(`Unsupported answer: ${c.id}. Only the displayed synthetic golden answer is implemented.`);
  }
  if (issues.length) return {status: 'UNSUPPORTED', issues};
  const missing = request.clarifications.filter(c => !input.answers[c.id]?.trim());
  const clarificationIssues = [...(dateRelationshipQuestion ? [dateRelationshipQuestion] : []), ...missing.map(c => c.topic)];
  if (clarificationIssues.length) return {status: 'AWAITING_CLARIFICATION', issues: clarificationIssues};
  return {status: 'READY_TO_CONFIRM', issues: []};
}

export function confirmRequirements(input: Submission, confirmed: boolean): RequirementsSnapshot {
  if (!confirmed || assessRequirements(input).status !== 'READY_TO_CONFIRM') throw new Error('Explicit confirmation of supported, complete requirements is required.');
  // Copy all original input bytes/values; no timestamp or hidden session state affects replay.
  return structuredClone({artifact_kind: 'RequirementsSnapshot', version: 1,
    processing: 'DETERMINISTIC_GOLDEN_FIXTURE',
    source: {fixture_version: request.fixture_version, request_id: request.request_id, schema_id: schema.schema_id},
    submission: input, confirmation: 'EXPLICIT_LOCAL_USER_CONFIRMATION', requirements: supportedRequirements});
}
