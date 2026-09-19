import * as pdfMake from 'pdfmake/build/pdfmake';
import pdfFonts from 'pdfmake/build/vfs_fonts';
import type {Content,ContentTable,StyleDictionary,TDocumentDefinitions} from 'pdfmake/interfaces';
import type {RequirementInterpretation,ReportDesign} from './foundry';
import type {DataStructure} from './schemaIngestion';
import type {TenantSettings} from './tenant';
import type {GuardrailDecision} from './guardrail';
import type {CandidateValidation,GenericCandidate} from './genericPowerBI';

export type DeploymentGuideInput={
 run:{id:string;generatedAt:string;applicationVersion:string};
 interpretation:Pick<RequirementInterpretation,'objective'|'businessQuestions'|'kpis'|'audience'|'pages'>;
 data:DataStructure;
 design:ReportDesign;
 tenant:TenantSettings;
 policy:GuardrailDecision;
 candidate:GenericCandidate;
 validation:CandidateValidation;
};

export type DeploymentGuideModel={
 organisation:string;reportName:string;purpose:string;audience:string;businessQuestions:string[];kpis:string[];
 projectName:string;semanticModel:string;report:string;pages:Array<{name:string;purpose:string;visuals:string[]}>;measures:string[];visualTypes:string[];
 sourceFormat:'CSV'|'XLSX';sourceFile:string;tables:Array<{name:string;columns:string[]}>;relationships:string[];prototypeSource:true;
 primaryColour:string;accentColour:string;themeName:string;runId:string;generatedAt:string;applicationVersion:string;validationOutcome:'PASS'|'FAIL';
 policyFindings:string[];warnings:string[];assumptions:string[];rlsRequirements:string[];
};

export type DeploymentGuideArtifact={filename:string;bytes:Uint8Array<ArrayBuffer>;model:DeploymentGuideModel};

const value=(text:string|undefined,fallback='To be confirmed')=>text?.trim()||fallback;
const colour=(text:string|undefined,fallback:string)=>/^#[0-9a-f]{6}$/i.test(text??'')?text!:fallback;
const list=(items:string[])=>items.map(item=>item.trim()).filter(Boolean);
const rlsPattern=/\b(?:RLS|row[- ]level security|security role)\b/i;

export function deploymentGuideFilename(reportName:string):string{
 const safe=reportName.normalize('NFKC').replace(/[\\/:*?"<>|\u0000-\u001f]/g,'-').replace(/[^\p{L}\p{N}._-]+/gu,'-').replace(/-{2,}/g,'-').replace(/^[._-]+|[._-]+$/g,'').slice(0,100);
 return`${safe||'Power-BI-Report'}-Deployment-Guide.pdf`;
}

export function createDeploymentGuideModel(input:DeploymentGuideInput):DeploymentGuideModel{
 const rlsRequirements=list(input.design.generationRequirements.filter(item=>rlsPattern.test(item)));
 const policyFindings=input.policy.evaluations.filter(item=>item.result!=='PASS').map(item=>`${item.ruleId}: ${item.reason}`);
 return{
  organisation:value(input.tenant.organisation.displayName||input.tenant.organisation.name,'Organisation'),
  reportName:value(input.design.projectName,'Power BI Report'),purpose:value(input.design.overview||input.interpretation.objective),audience:value(input.design.audience||input.interpretation.audience),
  businessQuestions:list(input.interpretation.businessQuestions),kpis:list(input.design.measures.map(item=>item.name).length?input.design.measures.map(item=>item.name):input.interpretation.kpis),
  projectName:input.candidate.projectName,semanticModel:`${input.candidate.projectName}.SemanticModel`,report:`${input.candidate.projectName}.Report`,
  pages:input.design.pages.map(page=>({name:page.name,purpose:page.purpose,visuals:page.visuals.map(visual=>`${visual.title} (${visual.type})`)})),
  measures:list(input.design.measures.map(item=>item.name)),visualTypes:[...new Set(input.design.pages.flatMap(page=>page.visuals.map(visual=>visual.type)))],
  sourceFormat:input.data.format,sourceFile:input.data.fileName,tables:input.data.tables.map(table=>({name:table.sourceName||table.name,columns:table.columns.map(column=>column.sourceName||column.name)})),
  relationships:input.data.relationships.map(item=>`${item.fromTable}.${item.fromColumn} to ${item.toTable}.${item.toColumn} (${item.cardinality})`),prototypeSource:true,
  primaryColour:colour(input.tenant.branding.primary,'#0F6CBD'),accentColour:colour(input.tenant.branding.accent,'#2D7D9A'),themeName:value(input.tenant.branding.themeName,'Tenant theme'),
  runId:value(input.run.id),generatedAt:value(input.run.generatedAt),applicationVersion:value(input.run.applicationVersion),validationOutcome:input.validation.status,
  policyFindings,warnings:list(input.design.warnings),assumptions:list(input.design.assumptions),rlsRequirements,
 };
}

const section=(title:string,body:Content|Content[],unbreakable=false):Content=>({stack:[{text:title,style:'sectionHeading'},...(Array.isArray(body)?body:[body])],margin:[0,12,0,2],unbreakable});
const bullets=(items:string[],empty='Not detected in this run.'):Content=>items.length?{ul:items,margin:[0,3,0,5]}:{text:empty,style:'muted',margin:[0,3,0,5]};
const table=(rows:string[][],widths:Array<number|'*'|'auto'>=['auto','*']):ContentTable=>({table:{headerRows:1,dontBreakRows:true,keepWithHeaderRows:1,widths,body:rows.map((row,index)=>row.map(cell=>({text:cell,bold:index===0,fillColor:index===0?'#F3F2F1':undefined,margin:[3,3,3,3]})))},layout:'lightHorizontalLines',margin:[0,4,0,8]});

export function deploymentGuideDocument(model:DeploymentGuideModel):TDocumentDefinitions{
 const generated=new Date(model.generatedAt);const generatedLabel=Number.isNaN(generated.valueOf())?model.generatedAt:generated.toLocaleString('en-AU',{dateStyle:'long',timeStyle:'short'});
 const remainingWarnings=[...model.warnings,...model.assumptions.map(item=>`Assumption: ${item}`),...model.policyFindings];
 const styles:StyleDictionary={title:{fontSize:21,bold:true,color:model.primaryColour,margin:[0,4,0,4]},subtitle:{fontSize:12,color:'#424242',margin:[0,0,0,10]},sectionHeading:{fontSize:14,bold:true,color:model.primaryColour,margin:[0,8,0,5]},minorHeading:{fontSize:10,bold:true,color:'#323130',margin:[0,5,0,2]},muted:{fontSize:9,color:'#605E5C'},callout:{fontSize:10,bold:true,color:'#7A2E00',fillColor:'#FFF4CE',margin:[8,8,8,8]},check:{fontSize:9,margin:[0,2,0,2]}};
 const checklist=['PBIP opens successfully in a supported Power BI Desktop version','Semantic model loads','Expected tables and relationships are present','Key measures return sensible results','Report pages render without visual errors','Slicers, filters and navigation operate correctly','Production connection is configured','Credentials are configured securely','Gateway is mapped and online if required','Data refresh succeeds',model.rlsRequirements.length?'RLS is tested using appropriate personas':'RLS applicability is confirmed','Target workspace is confirmed','Published report is validated','Business owner validates KPI definitions and results'];
 const content:Content[]=[
  {canvas:[{type:'rect',x:0,y:0,w:515,h:7,color:model.primaryColour}],margin:[0,0,0,12]},
  {text:model.organisation.toUpperCase(),fontSize:9,bold:true,color:model.accentColour,characterSpacing:1},
  {text:'POWER BI REPORT DEPLOYMENT & HANDOVER GUIDE',style:'title'},
  {text:model.reportName,style:'subtitle'},
  table([['Document metadata','Value'],['Generated',generatedLabel],['Run reference',model.runId],['Application version',model.applicationVersion],['Validation',model.validationOutcome],['Tenant theme',model.themeName]],['auto','*']),
  section('Report summary',[{text:model.purpose},{text:'Intended audience',style:'minorHeading'},{text:model.audience},{text:'Business questions and outcomes',style:'minorHeading'},bullets(model.businessQuestions),{text:'Key measures',style:'minorHeading'},bullets(model.kpis),{text:'Generated pages',style:'minorHeading'},bullets(model.pages.map(page=>`${page.name}: ${page.purpose}`))]),
  section('What APBRA generated',[table([['Generated component','Current candidate'],['PBIP project',model.projectName],['Report',model.report],['Semantic model',model.semanticModel],['Pages',model.pages.map(page=>page.name).join(', ')||'None'],['Measures',model.measures.join(', ')||'None'],['Visual types',model.visualTypes.join(', ')||'None'],['Deterministic validation',model.validationOutcome]],['auto','*'])]),
  section('Data structure and source summary',[{text:`${model.sourceFormat} schema/data used to generate the candidate: ${model.sourceFile}. The uploaded content is treated as request-specific prototype input.`},table([['Detected table','Important columns'],...model.tables.map(item=>[item.name,item.columns.join(', ')||'None detected'])],['auto','*']),{text:'Detected relationships',style:'minorHeading'},bullets(model.relationships),{text:'Production data connection',style:'minorHeading'},{text:'The generated candidate uses the supplied request data/schema. An approved production source and environment-specific connection still require configuration before deployment.'}]),
  section('Before deployment',bullets(['Replace prototype or synthetic input with the approved production source where applicable.','Configure the production data connection and credentials.','Gateway requirement: To be confirmed for the target environment.','Confirm the approved Power BI/Fabric workspace and publishing permissions.','Configure refresh requirements after credentials and any gateway binding are valid.',model.rlsRequirements.length?'Map generated RLS requirements to approved deployment-time users or groups.':'Confirm that no deployment-time RLS configuration is required.','Verify environment-specific parameters; none were inferred or invented by APBRA.'])),
  section('Credentials and security',[{text:'Credentials are not stored in the generated package. Configure credentials only through approved Power BI, Fabric or platform settings.'},{text:'Never enter passwords, API keys, access tokens or other secrets into APBRA report requirements. Production permissions and access configuration remain the responsibility of the customer or tenant.',margin:[0,5,0,0]}]),
  section('Opening the generated Power BI project',{ol:['Download the PBIP candidate.','Extract the downloaded ZIP.','Locate the generated .pbip project file.','Open the .pbip project using a compatible Power BI Desktop version.','Review the semantic model and report.','Configure the appropriate production data connection and credentials.','Refresh and validate the report before publishing.']}),
  section('Connection and gateway configuration',[{text:`Logical source requiring deployment mapping: ${model.tables.map(item=>item.name).join(', ')||'To be confirmed'}.`},{text:'Configure the environment-specific connection and credentials using approved platform settings. Gateway requirement: To be confirmed for the target environment. Verify connectivity with a successful refresh before publishing.',margin:[0,5,0,0]}],true),
  section('Workspace and publishing',{ol:['Select the approved Power BI or Fabric workspace.','Confirm that the publisher has the required workspace permissions.','Publish using the supported Power BI process after Desktop validation.','Confirm that the report and semantic model are present in the target workspace.','Validate intended user access after publishing.']}),
  section('Refresh configuration',[{text:'Configure credentials before refresh. If the target source requires a gateway, confirm that it is correctly bound and online. Configure an appropriate schedule only after the business requirement is confirmed, then complete at least one successful refresh test.'}]),
  section('RLS and access',model.rlsRequirements.length?[{text:'The Report Design contains the following RLS requirements:'},bullets(model.rlsRequirements),{text:'Map each requirement to approved deployment-time users or groups and validate access with appropriate test personas. No user or group identity has been invented by APBRA.'}]:[{text:'No RLS requirement was generated for this candidate.'}]),
  section('Post-deployment validation checklist',checklist.map(item=>({text:`[ ] ${item}`,style:'check'}))),
  section('Warnings and known limitations',[bullets(remainingWarnings,'No run-specific warnings or assumptions were recorded.'),{text:'APBRA’s current Power BI compiler supports a bounded subset of Power BI report capabilities. Successful generation does not imply universal Power BI feature compatibility.',margin:[0,5,0,0]}]),
  section('Changing the report later',[{text:'Update production source or endpoint configuration through approved platform settings. Schema changes, new measures, changed visuals, branding changes, or material requirement changes should trigger a new APBRA generation and validation cycle rather than silently altering an already validated candidate.'}],true),
  {text:'Generation and download of this package do not mean that the report has been deployed to production. Production connection configuration, credentials, workspace publishing, access configuration, refresh validation and business verification remain deployment activities.',style:'callout'},
 ];
 return{pageSize:'A4',pageMargins:[40,52,40,48],info:{title:`${model.reportName} - Deployment Guide`,author:model.organisation,subject:'Power BI report deployment and handover'},defaultStyle:{font:'Roboto',fontSize:9,lineHeight:1.25,color:'#242424'},styles,footer:(page,current)=>({columns:[{text:`APBRA · ${model.runId}`,fontSize:8,color:'#605E5C'},{text:`Page ${page} of ${current}`,alignment:'right',fontSize:8,color:'#605E5C'}],margin:[40,12,40,0]}),content};
}

export async function generateDeploymentGuide(input:DeploymentGuideInput):Promise<DeploymentGuideArtifact>{
 const model=createDeploymentGuideModel(input);const definition=deploymentGuideDocument(model);
 const bytes=await new Promise<Uint8Array<ArrayBuffer>>((resolve,reject)=>{try{pdfMake.createPdf(definition,undefined,undefined,pdfFonts).getBuffer(buffer=>resolve(new Uint8Array(buffer)))}catch(error){reject(error)}});
 if(bytes.length<8||new TextDecoder('latin1').decode(bytes.slice(0,8)).slice(0,5)!=='%PDF-')throw new Error('DEPLOYMENT_GUIDE_PDF_INVALID');
 return{filename:deploymentGuideFilename(model.reportName),bytes,model};
}
