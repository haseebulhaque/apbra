import type {ReportDesign,VisualDesign} from './foundry';
import type {DataStructure} from './schemaIngestion';

export type LayoutSlot={visualId:string;type:VisualDesign['type'];index:number;x:number;y:number;width:number;height:number;right:number;bottom:number};
export type PageLayout={pageId:string;pageName:string;width:1280;height:720;visuals:LayoutSlot[]};
export type NormalizationAction={code:'NORMALIZED_VISUAL_BINDING';reason:'MULTI_FIELD_SLICER_EXPANDED'|'DUPLICATE_BINDING_COLLAPSED'|'MIXED_BINDINGS_EXPANDED';pageId:string;pageName:string;originalVisualId:string;originalVisualType:'slicer';originalBindings:string[];originalLayoutSlot:LayoutSlot;resultingVisualIds:string[];resultingBindings:string[];layoutSlots:LayoutSlot[]};
export type NormalizationFinding={code:'EMPTY_SLICER_BINDING'|'MEASURE_BOUND_SLICER'|'UNKNOWN_SCHEMA_FIELD'|'LAYOUT_CAPACITY_EXCEEDED';pageId:string;pageName:string;visualId:string;reason:string;recommendedAction:string;requestedResultingVisuals?:number;pageBounds?:{width:1280;height:720};attemptedLayoutSlots?:LayoutSlot[]};
export type ReportDesignNormalization={status:'UNCHANGED'|'NORMALIZED'|'FAILED';originalReportDesign:ReportDesign;normalizedReportDesign:ReportDesign;originalVisualCount:number;normalizedVisualCount:number;normalizationActions:NormalizationAction[];normalizationFindings:NormalizationFinding[];pageLayouts:PageLayout[]};

export function isLayoutRepairEligible(normalization:ReportDesignNormalization):boolean{return normalization.status==='FAILED'&&normalization.normalizationFindings.length>0&&normalization.normalizationFindings.every(finding=>finding.code==='LAYOUT_CAPACITY_EXCEEDED')}

const PAGE_WIDTH=1280 as const,PAGE_HEIGHT=720 as const;
const canonical=(value:string)=>value.trim().toLowerCase();
const hash=(value:string)=>{let result=0x811c9dc5;for(const char of value)result=Math.imul(result^char.charCodeAt(0),16777619)>>>0;return result.toString(16).padStart(8,'0')};
const slug=(binding:string)=>{const value=binding.split('.').at(-1)??binding;return value.normalize('NFKD').replace(/[\u0300-\u036f]/g,'').replace(/[^A-Za-z0-9]+/g,'').slice(0,28)||'Field'};
const layout=(visual:VisualDesign,index:number):LayoutSlot=>{const x=20+(index%2)*610,y=30+Math.floor(index/2)*260,width=visual.type==='card'?285:580,height=visual.type==='card'?120:230;return{visualId:visual.id,type:visual.type,index,x,y,width,height,right:x+width,bottom:y+height}};
const withinPage=(slot:LayoutSlot)=>slot.x>=0&&slot.y>=0&&slot.right<=PAGE_WIDTH&&slot.bottom<=PAGE_HEIGHT;
const countVisuals=(design:ReportDesign)=>design.pages.reduce((count,page)=>count+page.visuals.length,0);

export function normalizeReportDesign(originalReportDesign:ReportDesign,schema:DataStructure):ReportDesignNormalization{
 const normalizedReportDesign=structuredClone(originalReportDesign),actions:NormalizationAction[]=[],findings:NormalizationFinding[]=[],pageLayouts:PageLayout[]=[];
 const knownFields=new Set(schema.tables.flatMap(table=>table.columns.map(column=>canonical(`${table.name}.${column.name}`))));
 for(const page of normalizedReportDesign.pages){
  const originalPage=originalReportDesign.pages.find(item=>item.id===page.id)??page,usedIds=new Set(page.visuals.map(visual=>visual.id)),normalized:VisualDesign[]=[],additional:VisualDesign[]=[];
  for(let originalIndex=0;originalIndex<page.visuals.length;originalIndex++){
   const visual=page.visuals[originalIndex];if(visual.type!=='slicer'){normalized.push(visual);continue}
   const sourceBindings=[...visual.fields.map(item=>item.trim()).filter(Boolean),...(visual.categoryField.trim()?[visual.categoryField.trim()]:[])],uniqueBindings:string[]=[],seen=new Set<string>();
   for(const binding of sourceBindings){const key=canonical(binding);if(!seen.has(key)){seen.add(key);uniqueBindings.push(binding)}}
   if(visual.measureIds.length){findings.push({code:'MEASURE_BOUND_SLICER',pageId:page.id,pageName:page.name,visualId:visual.id,reason:`Slicer '${visual.title}' contains ${visual.measureIds.length} measure binding(s).`,recommendedAction:'Use ordinary schema fields for slicers and keep measures in supported data visuals.'});normalized.push(visual);continue}
   if(!sourceBindings.length){findings.push({code:'EMPTY_SLICER_BINDING',pageId:page.id,pageName:page.name,visualId:visual.id,reason:`Slicer '${visual.title}' has no field or category binding.`,recommendedAction:'Provide exactly one known schema field for the slicer.'});normalized.push(visual);continue}
   const unknown=uniqueBindings.filter(binding=>!knownFields.has(canonical(binding)));
   if(unknown.length){findings.push({code:'UNKNOWN_SCHEMA_FIELD',pageId:page.id,pageName:page.name,visualId:visual.id,reason:`Slicer '${visual.title}' references unknown schema field(s): ${unknown.join(', ')}.`,recommendedAction:'Use exact Table.Column identifiers present in the uploaded schema.'});normalized.push(visual);continue}
   const duplicateCollapsed=uniqueBindings.length<sourceBindings.length;if(uniqueBindings.length===1&&!duplicateCollapsed&&sourceBindings.length===1){normalized.push(visual);continue}
   usedIds.delete(visual.id);const resulting=uniqueBindings.map(binding=>{const root=`${visual.id}__${slug(binding)}__${hash(canonical(binding))}`;let id=root,suffix=2;while(usedIds.has(id))id=`${root}__${suffix++}`;usedIds.add(id);return{...visual,id,title:uniqueBindings.length===1?visual.title:`${visual.title} — ${binding.split('.').at(-1)??binding}`,fields:[binding],categoryField:'',measureIds:[]} as VisualDesign});
   normalized.push(resulting[0]);additional.push(...resulting.slice(1));const reason=duplicateCollapsed&&uniqueBindings.length===1?'DUPLICATE_BINDING_COLLAPSED':visual.fields.length&&visual.categoryField.trim()?'MIXED_BINDINGS_EXPANDED':'MULTI_FIELD_SLICER_EXPANDED';
   actions.push({code:'NORMALIZED_VISUAL_BINDING',reason,pageId:page.id,pageName:page.name,originalVisualId:visual.id,originalVisualType:'slicer',originalBindings:sourceBindings,originalLayoutSlot:layout(originalPage.visuals[originalIndex],originalIndex),resultingVisualIds:resulting.map(item=>item.id),resultingBindings:resulting.map(item=>item.fields[0]),layoutSlots:[]});
  }
  page.visuals=[...normalized,...additional];const slots=page.visuals.map(layout);pageLayouts.push({pageId:page.id,pageName:page.name,width:PAGE_WIDTH,height:PAGE_HEIGHT,visuals:slots});
  for(const action of actions.filter(item=>item.pageId===page.id))action.layoutSlots=action.resultingVisualIds.map(id=>slots.find(slot=>slot.visualId===id)!);
  const outside=slots.filter(slot=>!withinPage(slot));if(outside.length){const affected=actions.find(action=>action.pageId===page.id&&action.resultingVisualIds.some(id=>outside.some(slot=>slot.visualId===id)));findings.push({code:'LAYOUT_CAPACITY_EXCEEDED',pageId:page.id,pageName:page.name,visualId:affected?.originalVisualId??outside[0].visualId,requestedResultingVisuals:affected?.resultingVisualIds.length??1,pageBounds:{width:PAGE_WIDTH,height:PAGE_HEIGHT},attemptedLayoutSlots:outside,reason:`Page '${page.name}' cannot fit the normalized layout within ${PAGE_WIDTH} x ${PAGE_HEIGHT}; ${outside.map(slot=>`'${slot.visualId}' reaches right ${slot.right} and bottom ${slot.bottom}`).join(', ')}.`,recommendedAction:'Reduce page scope or split visuals across pages before generation.'})}
 }
 return{status:findings.length?'FAILED':actions.length?'NORMALIZED':'UNCHANGED',originalReportDesign,normalizedReportDesign,originalVisualCount:countVisuals(originalReportDesign),normalizedVisualCount:countVisuals(normalizedReportDesign),normalizationActions:actions,normalizationFindings:findings,pageLayouts};
}
