import branding from '../knowledge/corporate-branding.md?raw';
import modelling from '../knowledge/powerbi-modelling-standards.md?raw';
import design from '../knowledge/report-design-standards.md?raw';
import accessibility from '../knowledge/accessibility-standards.md?raw';
import deployment from '../knowledge/deployment-standards.md?raw';
import {embedTexts,type AIMetrics,type AIResult} from './foundry';

export type KnowledgeDocument={source:string;version:string;prefix:string;content:string};
export type KnowledgeChunk={chunkId:string;source:string;version:string;heading:string;text:string;tokenEstimate:number;citation:string};
export type RetrievedChunk=KnowledgeChunk&{score:number};
export type RagRetrieval={kind:'SEMANTIC_LOCAL_RAG';query:string;embeddingModel:string;chunksIndexed:number;topK:number;retrieved:RetrievedChunk[];indexMetrics:AIMetrics;queryMetrics:AIMetrics;strategy:string};
export type Embedder=(input:string[])=>Promise<AIResult<number[][]>>;

export const documents:KnowledgeDocument[]=[
  {source:'corporate-branding.md',version:'1.0.0',prefix:'CB',content:branding},
  {source:'powerbi-modelling-standards.md',version:'1.0.0',prefix:'PM',content:modelling},
  {source:'report-design-standards.md',version:'1.0.0',prefix:'RD',content:design},
  {source:'accessibility-standards.md',version:'1.0.0',prefix:'AC',content:accessibility},
  {source:'deployment-standards.md',version:'1.0.0',prefix:'DP',content:deployment},
];

/** Heading-aware chunks preserve one complete policy topic per chunk. The small
 * corpus does not need arbitrary 400-token cuts; zero overlap avoids duplicating
 * rules in ranking while source, version, heading and stable chunk IDs retain provenance. */
export function chunkDocuments(input:KnowledgeDocument[]=documents):KnowledgeChunk[]{
  return input.flatMap(document=>{
    const sections=document.content.split(/^##\s+/m).slice(1);
    return sections.map((section,index)=>{const [heading,...body]=section.trim().split(/\r?\n/);const text=`${heading.trim()}\n${body.join('\n').trim()}`;const chunkId=`${document.prefix}-${String(index+1).padStart(3,'0')}`;return {chunkId,source:document.source,version:document.version,heading:heading.trim(),text,tokenEstimate:Math.ceil(text.split(/\s+/).length*1.3),citation:`local-knowledge:${document.source}@${document.version}#${chunkId}`};});
  });
}
function cosine(a:number[],b:number[]){if(a.length!==b.length||!a.length)throw new Error('EMBEDDING_DIMENSION_MISMATCH');let dot=0,aa=0,bb=0;for(let i=0;i<a.length;i++){dot+=a[i]*b[i];aa+=a[i]*a[i];bb+=b[i]*b[i]}return dot/(Math.sqrt(aa)*Math.sqrt(bb)||1)}
type Index={chunks:KnowledgeChunk[];vectors:number[][];metrics:AIMetrics};
let cached:Promise<Index>|null=null;
export function clearRagIndex(){cached=null}
async function buildIndex(embedder:Embedder){const chunks=chunkDocuments();const result=await embedder(chunks.map(c=>c.text));return {chunks,vectors:result.value,metrics:result.metrics}}
export async function retrieveKnowledge(query:string,topK=3,embedder:Embedder=embedTexts):Promise<RagRetrieval>{
  if(!query.trim())throw new Error('RAG_QUERY_REQUIRED');
  if(embedder===embedTexts&&!cached)cached=buildIndex(embedder).catch(error=>{cached=null;throw error});
  const index=embedder===embedTexts?await cached!:await buildIndex(embedder);
  const queryResult=await embedder([query]);
  const retrieved=index.chunks.map((chunk,i)=>({...chunk,score:cosine(index.vectors[i],queryResult.value[0])})).sort((a,b)=>b.score-a.score||a.chunkId.localeCompare(b.chunkId)).slice(0,Math.min(topK,index.chunks.length));
  return {kind:'SEMANTIC_LOCAL_RAG',query,embeddingModel:queryResult.metrics.model,chunksIndexed:index.chunks.length,topK,retrieved,indexMetrics:index.metrics,queryMetrics:queryResult.metrics,strategy:'heading-aware policy chunks; exact cosine similarity; in-memory index; no overlap'};
}

export const retrievalEvaluation=[
  {query:'What colours and theme should the corporate report use?',expectedSource:'corporate-branding.md'},
  {query:'Which executive sales KPIs are required?',expectedSource:'powerbi-modelling-standards.md'},
  {query:'How should year-over-year date modelling work?',expectedSource:'powerbi-modelling-standards.md'},
  {query:'What accessibility and readability rules apply?',expectedSource:'accessibility-standards.md'},
  {query:'Which chart types should be used for comparisons?',expectedSource:'report-design-standards.md'},
  {query:'Does a Region slicer provide row-level security?',expectedSource:'powerbi-modelling-standards.md'},
  {query:'What must deployment handover evidence contain?',expectedSource:'deployment-standards.md'},
] as const;
export async function evaluateRetrieval(embedder:Embedder=embedTexts,k=3){const results=[];for(const item of retrievalEvaluation){const retrieval=await retrieveKnowledge(item.query,k,embedder);const hit=retrieval.retrieved.some(chunk=>chunk.source===item.expectedSource);results.push({...item,hit,retrieved:retrieval.retrieved.map(c=>c.citation)});}return {k,total:results.length,hits:results.filter(r=>r.hit).length,hitRate:results.filter(r=>r.hit).length/results.length,results};}
