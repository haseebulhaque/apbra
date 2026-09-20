import type {ReportDesign,VisualDesign} from './foundry';
import type {DataStructure} from './schemaIngestion';

export type NormalizationAction={code:'NORMALIZED_VISUAL_BINDING';reason:'MULTI_FIELD_SLICER_EXPANDED'|'DUPLICATE_BINDING_COLLAPSED'|'MIXED_BINDINGS_EXPANDED';pageId:string;pageName:string;originalVisualId:string;originalVisualType:'slicer';originalBindings:string[];resultingVisualIds:string[];resultingBindings:string[];layoutSlots:Array<{visualId:string;index:number;x:number;y:number;width:number;height:number}>};
export type NormalizationFinding={code:'EMPTY_SLICER_BINDING'|'MEASURE_BOUND_SLICER'|'UNKNOWN_SCHEMA_FIELD'|'LAYOUT_CAPACITY_EXCEEDED';pageId:string;pageName:string;visualId:string;reason:string;recommendedAction:string};
export type ReportDesignNormalization={status:'UNCHANGED'|'NORMALIZED'|'FAILED';originalReportDesign:ReportDesign;normalizedReportDesign:ReportDesign;originalVisualCount:number;normalizedVisualCount:number;normalizationActions:NormalizationAction[];normalizationFindings:NormalizationFinding[]};

const MAX_BOUNDED_VISUALS_PER_PAGE=12;
const canonical=(value:string)=>value.trim().toLowerCase();
const hash=(value:string)=>{let result=0x811c9dc5;for(const char of value)result=Math.imul(result^char.charCodeAt(0),16777619)>>>0;return result.toString(16).padStart(8,'0')};
const slug=(binding:string)=>{const value=binding.split('.').at(-1)??binding;return value.normalize('NFKD').replace(/[\u0300-\u036f]/g,'').replace(/[^A-Za-z0-9]+/g,'').slice(0,28)||'Field'};
const layout=(visualId:string,index:number,visual:VisualDesign)=>({visualId,index,x:20+(index%2)*610,y:30+Math.floor(index/2)*260,width:visual.type==='card'?285:580,height:visual.type==='card'?120:230});
const countVisuals=(design:ReportDesign)=>design.pages.reduce((count,page)=>count+page.visuals.length,0);

export function normalizeReportDesign(originalReportDesign:ReportDesign,schema:DataStructure):ReportDesignNormalization{
 const normalizedReportDesign=structuredClone(originalReportDesign),actions:NormalizationAction[]=[],findings:NormalizationFinding[]=[];
 const knownFields=new Set(schema.tables.flatMap(table=>table.columns.map(column=>canonical(`${table.name}.${column.name}`))));
 for(const page of normalizedReportDesign.pages){
  const originalPage=originalReportDesign.pages.find(item=>item.id===page.id)??page;
  const usedIds=new Set(page.visuals.map(visual=>visual.id));
  const actionByOriginal=new Map<string,NormalizationAction>();
  const normalized:VisualDesign[]=[];
  for(const visual of page.visuals){
   if(visual.type!=='slicer'){normalized.push(visual);continue}
   const sourceBindings=[...visual.fields.map(item=>item.trim()).filter(Boolean),...(visual.categoryField.trim()?[visual.categoryField.trim()]:[])];
   const uniqueBindings:string[]=[];const seen=new Set<string>();
   for(const binding of sourceBindings){const key=canonical(binding);if(!seen.has(key)){seen.add(key);uniqueBindings.push(binding)}}
   if(visual.measureIds.length){findings.push({code:'MEASURE_BOUND_SLICER',pageId:page.id,pageName:page.name,visualId:visual.id,reason:`Slicer '${visual.title}' contains ${visual.measureIds.length} measure binding(s).`,recommendedAction:'Use ordinary schema fields for slicers and keep measures in supported data visuals.'});normalized.push(visual);continue}
   if(!sourceBindings.length){findings.push({code:'EMPTY_SLICER_BINDING',pageId:page.id,pageName:page.name,visualId:visual.id,reason:`Slicer '${visual.title}' has no field or category binding.`,recommendedAction:'Provide exactly one known schema field for the slicer.'});normalized.push(visual);continue}
   const unknown=uniqueBindings.filter(binding=>!knownFields.has(canonical(binding)));
   if(unknown.length){findings.push({code:'UNKNOWN_SCHEMA_FIELD',pageId:page.id,pageName:page.name,visualId:visual.id,reason:`Slicer '${visual.title}' references unknown schema field(s): ${unknown.join(', ')}.`,recommendedAction:'Use exact Table.Column identifiers present in the uploaded schema.'});normalized.push(visual);continue}
   const duplicateCollapsed=uniqueBindings.length<sourceBindings.length;
   if(uniqueBindings.length===1&&!duplicateCollapsed&&sourceBindings.length===1){normalized.push(visual);continue}
   usedIds.delete(visual.id);
   const resulting=uniqueBindings.map((binding,index)=>{
    const root=`${visual.id}__${slug(binding)}__${hash(canonical(binding))}`;let id=root,suffix=2;while(usedIds.has(id))id=`${root}__${suffix++}`;usedIds.add(id);
    return{...visual,id,title:uniqueBindings.length===1?visual.title:`${visual.title} — ${binding.split('.').at(-1)??binding}`,fields:[binding],categoryField:'',measureIds:[]};
   });
   normalized.push(...resulting);
   const reason=duplicateCollapsed&&uniqueBindings.length===1?'DUPLICATE_BINDING_COLLAPSED':visual.fields.length&&visual.categoryField.trim()?'MIXED_BINDINGS_EXPANDED':'MULTI_FIELD_SLICER_EXPANDED';
   const action:NormalizationAction={code:'NORMALIZED_VISUAL_BINDING',reason,pageId:page.id,pageName:page.name,originalVisualId:visual.id,originalVisualType:'slicer',originalBindings:sourceBindings,resultingVisualIds:resulting.map(item=>item.id),resultingBindings:resulting.map(item=>item.fields[0]),layoutSlots:[]};
   actions.push(action);actionByOriginal.set(visual.id,action);
  }
  page.visuals=normalized;
  for(const action of actionByOriginal.values())action.layoutSlots=action.resultingVisualIds.map(id=>{const index=page.visuals.findIndex(item=>item.id===id);return layout(id,index,page.visuals[index])});
  if(page.visuals.length>MAX_BOUNDED_VISUALS_PER_PAGE&&page.visuals.length>originalPage.visuals.length)findings.push({code:'LAYOUT_CAPACITY_EXCEEDED',pageId:page.id,pageName:page.name,visualId:'',reason:`Normalization expands page '${page.name}' from ${originalPage.visuals.length} to ${page.visuals.length} visuals, above the bounded ${MAX_BOUNDED_VISUALS_PER_PAGE}-visual layout capacity.`,recommendedAction:'Split the page or reduce its visual scope before generation.'});
 }
 return{status:findings.length?'FAILED':actions.length?'NORMALIZED':'UNCHANGED',originalReportDesign,normalizedReportDesign,originalVisualCount:countVisuals(originalReportDesign),normalizedVisualCount:countVisuals(normalizedReportDesign),normalizationActions:actions,normalizationFindings:findings};
}
