export const stages = ['Requirement', 'Clarification', 'Governed Knowledge', 'DesignPlan', 'Generation', 'Validation'] as const;
export type Answers = Record<string, string>;
// UI draft validation only: does not create an authoritative RequirementsSnapshot.
export function draftReady(prompt: string, ids: string[], answers: Answers): boolean {
  return prompt.trim().length > 0 && prompt.length <= 4000 && ids.every(id => !!answers[id]?.trim());
}
export function unavailableStages() {
  return stages.map(name => ({name, status: 'NOT_RUN' as const}));
}
