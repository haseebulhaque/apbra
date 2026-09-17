import {validateDesignPlan, serializeDesignPlan, type DesignPlan} from './designPlan';
import date from '../../../tests/bootstrap/fixtures/sales-v1/DimDate.csv?raw';
import product from '../../../tests/bootstrap/fixtures/sales-v1/DimProduct.csv?raw';
import region from '../../../tests/bootstrap/fixtures/sales-v1/DimRegion.csv?raw';
import area from '../../../tests/bootstrap/fixtures/sales-v1/DimBusinessArea.csv?raw';
import customer from '../../../tests/bootstrap/fixtures/sales-v1/DimCustomer.csv?raw';
import sales from '../../../tests/bootstrap/fixtures/sales-v1/FactSales.csv?raw';
export type ProjectFiles = Record<string,string>;
export type Candidate = {kind:'PowerBICandidate'; generatorVersion:'capstone-pbip-1'; files:ProjectFiles; runtime:{desktop:'NOT_RUN';dax:'NOT_RUN';rls:'NOT_RUN'}; release:'NOT_ELIGIBLE'};
const csv:Record<string,string>={DimDate:date,DimProduct:product,DimRegion:region,DimBusinessArea:area,DimCustomer:customer,FactSales:sales};
const root='https://developer.microsoft.com/json-schemas/';
const schema=(name:string,version='1.0.0')=>root+`fabric/item/report/definition/${name}/${version}/schema.json`;
const json=(v:unknown)=>JSON.stringify(v,null,2)+'\n';
const field=(binding:string,measure=false)=>{const [table,column]=binding.split('.');return {[measure?'Measure':'Column']:{Expression:{SourceRef:{Entity:table}},Property:column}};};
const literal=(value:string)=>({expr:{Literal:{Value:value}}});
const quoted=(value:string)=>"'"+value.replaceAll("'","''")+"'";
const projection=(binding:string,measure=false)=>({field:field(binding,measure),queryRef:binding,nativeQueryRef:binding.split('.')[1]});

/** Only a revalidated golden DesignPlan enters rendering. CSVs are fixed synthetic
 * assets; no user text becomes executable M, path, DAX or a connection string. */
export function generatePowerBI(input:unknown):Candidate {
 validateDesignPlan(input);const plan:DesignPlan=structuredClone(input);
 const files:ProjectFiles={};const r=plan.projectName+'.Report',m=plan.projectName+'.SemanticModel';
 files[plan.projectName+'.pbip']=json({$schema:root+'fabric/pbip/pbipProperties/1.0.0/schema.json',version:'1.0',artifacts:[{report:{path:r}}],settings:{enableAutoRecovery:true}});
 files[r+'/definition.pbir']=json({$schema:root+'fabric/item/report/definitionProperties/2.0.0/schema.json',version:'4.0',datasetReference:{byPath:{path:'../'+m}}});
 files[m+'/definition.pbism']=json({$schema:root+'fabric/item/semanticModel/definitionProperties/1.0.0/schema.json',version:'4.0',settings:{}});
 files[m+'/definition/database.tmdl']='database\n\tcompatibilityLevel: 1601\n';
 files[m+'/definition/model.tmdl']='model Model\n\tculture: en-US\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n\tsourceQueryCulture: en-US\n\n'+plan.model.tables.map(t=>'ref table '+t.name).join('\n')+'\n';
 files[m+'/definition/relationships.tmdl']=plan.model.relationships.map((rel,i)=>`relationship golden-${i+1}\n\tfromColumn: ${rel.from_table}.${rel.from_column}\n\ttoColumn: ${rel.to_table}.${rel.to_column}\n\tfromCardinality: many\n\ttoCardinality: one\n\tcrossFilteringBehavior: oneDirection\n\tisActive: true\n`).join('\n');
 for(const table of plan.model.tables){
  // Fixed files have simple unquoted values. Csv.Document handles CSV parsing in M.
  const data=csv[table.name];if(!data)throw new Error('GENERATOR_UNSUPPORTED_TABLE');
  const encoded=btoa(data);const types:Record<string,string>={date:'date',integer:'Int64.Type',decimal:'Currency.Type',text:'text'};
  const columns=table.columns.map(c=>`\tcolumn ${c.name}\n\t\tdataType: ${{date:'dateTime',integer:'int64',decimal:'decimal',text:'string'}[c.type]}\n\t\tsourceColumn: ${c.name}\n\t\tsummarizeBy: none${c.name===table.primary_key?'\n\t\tisKey':''}${c.type==='date'?'\n\t\tformatString: yyyy-mm-dd':''}\n`).join('\n');
  const measures=table.name==='FactSales'?plan.model.measures.map(v=>`\tmeasure ${quoted(v.name)} = ${v.dax}\n\t\tformatString: ${'"'+v.format.replaceAll('"','""')+'"'}\n`).join('\n'):'';
  files[m+'/definition/tables/'+table.name+'.tmdl']=`table ${table.name}${table.name===plan.model.dateTable?'\n\tdataCategory: Time':''}\n\n${columns}\n${measures}\n\tpartition ${table.name} = m\n\t\tmode: import\n\t\tsource =\n\t\t\tlet\n\t\t\t\tSource = Csv.Document(Binary.FromText("${encoded}", BinaryEncoding.Base64), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),\n\t\t\t\tHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),\n\t\t\t\tTyped = Table.TransformColumnTypes(Headers, {${table.columns.map(c=>`{"${c.name}", ${types[c.type]==='text'||types[c.type]==='date'?'type ':''}${types[c.type]}}`).join(', ')}}, "en-US")\n\t\t\tin\n\t\t\t\tTyped\n`;
  files['data/'+table.file]=data;
 }
 files[r+'/definition/version.json']=json({$schema:schema('versionMetadata'),version:'4.0.0'});
 const filters=plan.filters.map((binding,i)=>({name:'filter-'+i,field:field(binding),type:'Categorical'}));
 const yearField=field('DimDate.Year');
 files[r+'/definition/report.json']=json({$schema:schema('report'),layoutOptimization:'None',themeCollection:{},filterConfig:{filters:[...filters,{name:'initial-year',field:yearField,type:'Categorical',filter:{Version:2,From:[{Name:'d',Entity:'DimDate',Type:0}],Where:[{Condition:{In:{Expressions:[{Column:{Expression:{SourceRef:{Source:'d'}},Property:'Year'}}],Values:[[{Literal:{Value:plan.initialYear+'L'}}]]}}}]}}]}});
 files[r+'/definition/pages/pages.json']=json({$schema:schema('pagesMetadata'),pageOrder:plan.pages.map(p=>p.id),activePageName:plan.pages[0].id});
 for(const page of plan.pages){
  const path=r+'/definition/pages/'+page.id;
  files[path+'/page.json']=json({$schema:schema('page','2.0.0'),name:page.id,displayName:page.name,displayOption:'FitToPage',width:1280,height:960,objects:{background:[{properties:{color:{solid:{color:literal(quoted(plan.theme.background))}},transparency:literal('0D')}}]}});
  const visuals=[...page.visuals,...plan.filters.map((axis,i)=>({id:'slicer-'+i,kind:'slicer',axis,measureIds:[],title:axis.split('.')[1],altText:axis.split('.')[1]}))];
  visuals.forEach((v,i)=>{
   const measures=v.measureIds.map(id=>projection('FactSales.'+plan.model.measures.find(m=>m.id===id)!.name,true));
   const axis=v.axis?[projection(v.axis)]:[];
   const queryState=v.kind==='card'?{Values:{projections:measures}}:v.kind==='table'?{Values:{projections:[...axis,...measures]}}:v.kind==='slicer'?{Values:{projections:axis}}:{Category:{projections:axis},Y:{projections:measures}};
   files[path+'/visuals/'+v.id+'/visual.json']=json({$schema:schema('visualContainer','2.0.0'),name:v.id,position:{x:20+(i%4)*315,y:20+Math.floor(i/4)*310,z:i,width:295,height:285,tabOrder:i},visual:{visualType:({card:'card',line:'lineChart',bar:'clusteredBarChart',table:'tableEx',slicer:'slicer'} as Record<string,string>)[v.kind],query:{queryState},objects:{dataPoint:[{properties:{defaultColor:{solid:{color:literal(quoted(plan.theme.primary))}}}}]},visualContainerObjects:{title:[{properties:{show:literal('true'),text:literal(quoted(v.title)),fontColor:{solid:{color:literal(quoted(plan.theme.foreground))}}}}],general:[{properties:{altText:literal(quoted(v.altText))}}]}}});
  });
 }
 files['DesignPlan.json']=serializeDesignPlan(plan);
 files['README.txt']='APBRA synthetic Capstone candidate; NOT AN APPROVED RELEASE.\nExtract the entire ZIP and open SalesPerformance.pbip in Power BI Desktop with PBIP/PBIR preview enabled. Refresh to load embedded synthetic CSV data; no credentials or external source are required.\nGenerated source files and data are real. Desktop open/refresh, numeric DAX and RLS runtime checks: NOT_RUN. Do not claim compatibility or successful deployment.\nOnly the validated golden plan is supported. No RLS roles, custom visuals, publishing or arbitrary input execution.\n';
 return {kind:'PowerBICandidate',generatorVersion:'capstone-pbip-1',files,runtime:{desktop:'NOT_RUN',dax:'NOT_RUN',rls:'NOT_RUN'},release:'NOT_ELIGIBLE'};
}
