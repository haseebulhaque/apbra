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
const projection=(binding:string,measure=false)=>({field:field(binding,measure),queryRef:binding,nativeQueryRef:binding.split('.')[1],active:true});
const visualIds={
 page:'a7d58f91c3e04b26a145',
 totalSales:'0a1b2c3d4e5f60718293',
 totalOrders:'1b2c3d4e5f60718293a4',
 averageOrderValue:'2c3d4e5f60718293a4b5',
 salesYoyPercent:'3d4e5f60718293a4b5c6',
 salesByRegion:'4e5f60718293a4b5c6d7',
 regionSlicer:'5f60718293a4b5c6d7e8',
 categorySlicer:'60718293a4b5c6d7e8f9',
} as const;
const visualContainerObjects=(title:string,showTitle=true)=>({
 title:[{properties:{show:literal(showTitle?'true':'false'),...(showTitle?{text:literal(quoted(title))}:{})}}],
 background:[{properties:{show:literal('true'),color:{solid:{color:literal("'#FFFFFF'")}},transparency:literal('0D')}}],
 border:[{properties:{show:literal('true'),color:{solid:{color:literal("'#D9D9D9'")}},radius:literal('5D'),width:literal('1D')}}],
});

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
 // These report-definition versions and resource bindings mirror a PBIR project
 // saved successfully by Power BI Desktop 2.157.1354.0. Runtime compatibility is
 // still established only by a separate Desktop-open test.
 files[r+'/definition/version.json']=json({$schema:schema('versionMetadata'),version:'2.0.0'});
 files[r+'/definition/report.json']=json({$schema:schema('report','3.3.0'),themeCollection:{customTheme:{name:'SalesPerformanceTheme.json',reportVersionAtImport:{visual:'2.9.0',report:'3.3.0',page:'2.1.0'},type:'RegisteredResources'}},resourcePackages:[{name:'RegisteredResources',type:'RegisteredResources',items:[{name:'SalesPerformanceTheme.json',path:'SalesPerformanceTheme.json',type:'CustomTheme'}]}]});
 files[r+'/StaticResources/RegisteredResources/SalesPerformanceTheme.json']=json({name:'Sales Performance Demo',dataColors:[plan.theme.primary,'#2D7D9A','#7FBA00','#FFB900'],background:plan.theme.background,foreground:plan.theme.foreground,tableAccent:plan.theme.primary,good:'#107C10',neutral:'#797775',bad:'#D13438'});
 files[r+'/definition/pages/pages.json']=json({$schema:schema('pagesMetadata','1.1.0'),pageOrder:[visualIds.page],activePageName:visualIds.page});
 const pagePath=r+'/definition/pages/'+visualIds.page;
 files[pagePath+'/page.json']=json({$schema:schema('page','2.1.0'),name:visualIds.page,displayName:'Executive Summary',displayOption:'FitToPage',height:720,width:1280,objects:{background:[{properties:{color:{solid:{color:literal(quoted(plan.theme.background))}},transparency:literal('0D')}}]}});
 const cardSpecs=[
  [visualIds.totalSales,'Total Sales',20,'Total Sales'],
  [visualIds.totalOrders,'Total Orders',325,'Total Orders'],
  [visualIds.averageOrderValue,'Average Order Value',630,'Average Order Value'],
  [visualIds.salesYoyPercent,'Sales YoY %',935,'Sales YoY %'],
 ] as const;
 cardSpecs.forEach(([id,title,x,measure],index)=>{
  files[pagePath+'/visuals/'+id+'/visual.json']=json({$schema:schema('visualContainer','2.9.0'),name:id,position:{x,y:30,z:1100,width:285,height:100,tabOrder:index+1},visual:{visualType:'cardVisual',query:{queryState:{Data:{projections:[projection('FactSales.'+measure,true)]}}},objects:{label:[{properties:{show:literal('true'),text:literal(quoted(title))},selector:{id:'default'}}]},visualContainerObjects:visualContainerObjects(title,false)}});
 });
 files[pagePath+'/visuals/'+visualIds.salesByRegion+'/visual.json']=json({$schema:schema('visualContainer','2.9.0'),name:visualIds.salesByRegion,position:{x:20,y:165,z:1000,width:800,height:500,tabOrder:5},visual:{visualType:'barChart',query:{queryState:{Category:{projections:[projection('DimRegion.RegionName')]},Y:{projections:[projection('FactSales.Total Sales',true)]}}},objects:{legend:[{properties:{show:literal('false')}}],valueAxis:[{properties:{show:literal('true'),gridlineShow:literal('false')}}],labels:[{properties:{show:literal('true')}}]},visualContainerObjects:visualContainerObjects('Sales by region')}});
 const slicers=[
  [visualIds.regionSlicer,'Region','DimRegion.RegionName',165],
  [visualIds.categorySlicer,'Product category','DimProduct.ProductCategory',420],
 ] as const;
 slicers.forEach(([id,title,binding,y],index)=>{
  files[pagePath+'/visuals/'+id+'/visual.json']=json({$schema:schema('visualContainer','2.9.0'),name:id,position:{x:850,y,z:1000,width:370,height:220,tabOrder:index+6},visual:{visualType:'slicer',query:{queryState:{Values:{projections:[projection(binding)]}}},visualContainerObjects:visualContainerObjects(title)}});
 });
 files['DesignPlan.json']=serializeDesignPlan(plan);
 files['README.txt']='APBRA synthetic Capstone Desktop-test candidate; NOT AN APPROVED RELEASE.\nExtract the entire ZIP and open SalesPerformance.pbip in Power BI Desktop with PBIP/PBIR preview enabled. Refresh to load embedded synthetic CSV data; no credentials or external source are required.\nThe report is intentionally reduced to one page, four KPI cards, one bar chart and two slicers using PBIR structures adapted from a project saved by Desktop 2.157.1354.0.\nGenerated source files and data are real. Desktop open/render/refresh, numeric DAX and RLS runtime checks: NOT_RUN. A successful JSON or source validation is not Desktop compatibility evidence.\nNo RLS roles, custom visuals, publishing or arbitrary input execution.\n';
 return {kind:'PowerBICandidate',generatorVersion:'capstone-pbip-1',files,runtime:{desktop:'NOT_RUN',dax:'NOT_RUN',rls:'NOT_RUN'},release:'NOT_ELIGIBLE'};
}
