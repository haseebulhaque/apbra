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

// Preserve source identity before JSON.parse can round geometry or design versions.
// Large exactly representable integers remain valid; this is not a magnitude cap.
function decimal(value:string){
 const [mantissa,exponentText]=value.toLowerCase().split('e'),negative=mantissa.startsWith('-'),unsigned=negative?mantissa.slice(1):mantissa;
 const fractional=unsigned.includes('.')?unsigned.length-unsigned.indexOf('.')-1:0;
 let digits=unsigned.replace('.','').replace(/^0+/,''),exponent=Number(exponentText??0)-fractional;
 if(!digits)return{digits:'0',exponent:0,negative:false};
 const zeros=digits.match(/0+$/)?.[0].length??0;digits=digits.slice(0,digits.length-zeros);exponent+=zeros;
 return{digits,exponent,negative};
}
export function geometryNumberPreserved(token:string):boolean{
 const value=Number(token);if(!Number.isFinite(value))return false;
 const original=decimal(token);if(original.digits==='0')return value===0;
 if(value===0)return false;
 if(Number.isInteger(value)){
  if(original.exponent<0)return false;
  const represented=BigInt(value).toString(),sign=original.negative?'-':'';
  // Compare lengths first, so an enormous exponent never allocates a string.
  if(sign.length+original.digits.length+original.exponent!==represented.length)return false;
  return sign+original.digits+'0'.repeat(original.exponent)===represented;
 }
 const represented=decimal(value.toString());
 return original.digits===represented.digits&&original.exponent===represented.exponent&&original.negative===represented.negative;
}
export function assertGeometryJSONNumbers(raw:string):void{
 // Validate JSON syntax first. The token walk reads string keys, not rounded values.
 JSON.parse(raw);let cursor=0;
 const whitespace=()=>{while(/\s/.test(raw[cursor]??'')&&cursor<raw.length)cursor++};
 const string=()=>{const start=cursor++;while(cursor<raw.length){const char=raw[cursor++];if(char==='\\'){cursor++;continue}if(char==='"')break}return JSON.parse(raw.slice(start,cursor)) as string};
 const isGeometry=(path:Array<string|number>)=>{const last=path.at(-1);return path.at(-2)==='position'&&path.at(-4)==='visuals'&&path.at(-6)==='pages'&&['x','y','width','height','z','tabOrder','angle'].includes(String(last))||path.at(-3)==='pages'&&['width','height'].includes(String(last))};
 const isDesignVersion=(path:Array<string|number>)=>path.at(-1)==='schema_version'&&(path.length===1||path.length===2&&['reportDesign','report_design'].includes(String(path[0])));
 const walk=(path:Array<string|number>):void=>{
  whitespace();const char=raw[cursor];
  if(char==='{'){cursor++;whitespace();if(raw[cursor]==='}'){cursor++;return}while(cursor<raw.length){whitespace();const key=string();whitespace();cursor++;walk([...path,key]);whitespace();if(raw[cursor++]==='}')return}return}
  if(char==='['){cursor++;whitespace();if(raw[cursor]===']'){cursor++;return}let index=0;while(cursor<raw.length){walk([...path,index++]);whitespace();if(raw[cursor++]===']')return}return}
  if(char==='"'){string();return}
  const token=raw.slice(cursor).match(/^(?:-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null)/)?.[0];
  if(!token)throw new Error('REPORT_DESIGN_GEOMETRY_INVALID');cursor+=token.length;
  if((isGeometry(path)||isDesignVersion(path))&&token!=='null'&&token!=='true'&&token!=='false'&&!geometryNumberPreserved(token))throw new Error('REPORT_DESIGN_GEOMETRY_UNREPRESENTABLE');
 };
 walk([]);
}

/** JSON's shortest integer spelling can itself change an exact large integer. */
export function stringifyExactNumbers(value:unknown,space=0):string{
 const indent=' '.repeat(Math.min(10,Math.max(0,space))),active=new Set<object>();
 const encode=(input:unknown,depth:number):string|undefined=>{
  if(input===null)return'null';
  if(typeof input==='number')return Number.isFinite(input)?Number.isInteger(input)?BigInt(input).toString():JSON.stringify(input):'null';
  if(typeof input==='string'||typeof input==='boolean')return JSON.stringify(input);
  if(typeof input==='bigint')throw new TypeError('BigInt is not a JSON number');
  if(typeof input!=='object')return undefined;
  if(active.has(input))throw new TypeError('Circular JSON value');active.add(input);
  const pad=indent.repeat(depth+1),close=indent.repeat(depth);
  const array=Array.isArray(input),parts=array?Array.from(input,item=>encode(item,depth+1)??'null'):Object.entries(input).flatMap(([key,item])=>{const encoded=encode(item,depth+1);return encoded===undefined?[]:[JSON.stringify(key)+(indent?': ':':')+encoded]});
  active.delete(input);const [open,end]=array?['[',']']:['{','}'];
  return parts.length?open+(indent?'\n'+pad:'')+parts.join(indent?',\n'+pad:',')+(indent?'\n'+close:'')+end:open+end;
 };
 const encoded=encode(value,0);if(encoded===undefined)throw new TypeError('A JSON value is required');return encoded;
}
