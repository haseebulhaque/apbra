/** PBIR representation, not report quality or layout policy. */
export const pageDisplayOptions=['DeprecatedDynamic','FitToPage','FitToWidth','ActualSize','ActualSizeTopLeft'] as const;
export type PageDisplayOption=typeof pageDisplayOptions[number];
export type AIVisualPosition={x:number;y:number;width:number;height:number;z?:number|null;tabOrder?:number|null;angle?:number|null};
export type AIPageGeometry={displayOption:PageDisplayOption;width?:number|null;height?:number|null};
export const geometryFormat={designVersion:2,pageSchema:'2.1.0',visualSchema:'2.9.0',requiredPosition:['x','y','width','height'],optionalPosition:['z','tabOrder','angle'],pageDisplayOptions,optionalPageNumbers:['width','height'],geometryBinding:'AI_AUTHORED_EXACT'} as const;
const object=(value:unknown):Record<string,unknown>=>{if(!value||typeof value!=='object'||Array.isArray(value))throw new Error('REPORT_DESIGN_GEOMETRY_INVALID');return value as Record<string,unknown>};
const number=(value:unknown)=>typeof value==='number'&&Number.isFinite(value);
const optional=(value:unknown)=>value===null||value===undefined||number(value);
export function visualPosition(value:unknown):Record<string,number>{
 const position=object(value),required=['x','y','width','height'],optionalKeys=['z','tabOrder','angle'];
 if(Object.keys(position).some(key=>![...required,...optionalKeys].includes(key))||required.some(key=>!number(position[key]))||optionalKeys.some(key=>!optional(position[key])))throw new Error('REPORT_DESIGN_GEOMETRY_INVALID');
 return Object.fromEntries(Object.entries(position).filter(([,value])=>value!==null&&value!==undefined)) as Record<string,number>;
}
export function pageGeometry(value:unknown):{displayOption:PageDisplayOption;width?:number;height?:number}{
 const page=object(value);
 if(Object.keys(page).some(key=>!['id','name','purpose','visuals','displayOption','width','height'].includes(key)))throw new Error('REPORT_DESIGN_GEOMETRY_INVALID');
 if(!pageDisplayOptions.includes(page.displayOption as PageDisplayOption)||!optional(page.width)||!optional(page.height))throw new Error('REPORT_DESIGN_GEOMETRY_INVALID');
 return{displayOption:page.displayOption as PageDisplayOption,...(page.width===null||page.width===undefined?{}:{width:page.width as number}),...(page.height===null||page.height===undefined?{}:{height:page.height as number})};
}
export function assertAuthoredGeometry(value:unknown):void{
 const design=object(value);
 if(design.schema_version===1)throw new Error('AI_AUTHORED_GEOMETRY_REQUIRED: This saved design has no AI-authored geometry. Use Create another design to request a fresh proposal; existing report files remain available.');
 if(design.schema_version!==2||!Array.isArray(design.pages))throw new Error('REPORT_DESIGN_GEOMETRY_INVALID');
 for(const p of design.pages){const page=object(p);pageGeometry(page);if(!Array.isArray(page.visuals))throw new Error('REPORT_DESIGN_GEOMETRY_INVALID');for(const item of page.visuals){const visual=object(item);if(Object.keys(visual).some(key=>!['id','type','title','categoryField','timeGrain','measureIds','fields','altText','position'].includes(key)))throw new Error('REPORT_DESIGN_GEOMETRY_INVALID');visualPosition(visual.position)}}
}
