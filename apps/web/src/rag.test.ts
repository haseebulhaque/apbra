import {expect,it} from 'vitest';
import {chunkDocuments,evaluateRetrieval,retrieveKnowledge,type Embedder} from './rag';

const terms=['theme','sales kpi','date year','accessibility contrast','chart visual','security rls','handover deployment'];
const embedder:Embedder=async inputs=>({value:inputs.map(text=>terms.map(term=>term.split(' ').some(word=>text.toLowerCase().includes(word))?1:0)),metrics:{model:'test-embedding',latencyMs:1,promptTokens:1,completionTokens:null,totalTokens:1}});
it('uses stable heading-aware chunks with complete provenance and no overlap',()=>{
  const chunks=chunkDocuments();expect(chunks).toHaveLength(10);expect(new Set(chunks.map(c=>c.chunkId)).size).toBe(10);for(const chunk of chunks){expect(chunk.citation).toContain(chunk.source);expect(chunk.version).toBe('1.0.0');expect(chunk.text).toContain(chunk.heading);expect(chunk.tokenEstimate).toBeGreaterThan(5)}
});
it('performs exact cosine retrieval and retains citations',async()=>{
  const result=await retrieveKnowledge('accessible report contrast and keyboard order',3,embedder);expect(result.kind).toBe('SEMANTIC_LOCAL_RAG');expect(result.chunksIndexed).toBe(10);expect(result.retrieved).toHaveLength(3);expect(result.retrieved[0].source).toBe('accessibility-standards.md');expect(result.retrieved[0].citation).toContain('#AC-001');
});
it('measures the representative retrieval set at Hit@3',async()=>{
  const result=await evaluateRetrieval(embedder,3);expect(result.total).toBe(7);expect(result.hits).toBe(7);expect(result.hitRate).toBe(1);
});
