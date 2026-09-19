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

const invalidDocumentCodePoint=(codePoint:number)=>
 codePoint<=0x8||(codePoint>=0xb&&codePoint<=0x1f)||(codePoint>=0x7f&&codePoint<=0x9f)||
 (codePoint>=0xd800&&codePoint<=0xdfff)||(codePoint>=0xfdd0&&codePoint<=0xfdef)||(codePoint&0xffff)===0xfffe||(codePoint&0xffff)===0xffff;

export function normalizeDocumentText(text:string):string{
 const normalized=text.normalize('NFC').replace(/\r\n?|[\n\t\u2028\u2029]/g,' ');
 return Array.from(normalized).filter(character=>{
  const codePoint=character.codePointAt(0)!;
  return !invalidDocumentCodePoint(codePoint)&&codePoint!==0xad&&codePoint!==0xfeff&&codePoint!==0x200b&&codePoint!==0x200e&&codePoint!==0x200f&&!(codePoint>=0x202a&&codePoint<=0x202e)&&!(codePoint>=0x2060&&codePoint<=0x206f);
 }).join('').replace(/\s{2,}/g,' ').trim();
}

const value=(text:string|undefined,fallback='To be confirmed')=>normalizeDocumentText(text??'')||fallback;
const colour=(text:string|undefined,fallback:string)=>/^#[0-9a-f]{6}$/i.test(text??'')?text!:fallback;
const list=(items:string[])=>items.map(normalizeDocumentText).filter(Boolean);
const rlsPattern=/\b(?:RLS|row[- ]level security|security role)\b/i;
export const DEPLOYMENT_GUIDE_FILENAME='Report-Deployment-Guide.pdf';

export function createDeploymentGuideModel(input:DeploymentGuideInput):DeploymentGuideModel{
 const rlsRequirements=list(input.design.generationRequirements).filter(item=>rlsPattern.test(item));
 const policyFindings=input.policy.evaluations.filter(item=>item.result!=='PASS').map(item=>`${value(item.ruleId)}: ${value(item.reason)}`);
 return{
  organisation:value(input.tenant.organisation.displayName||input.tenant.organisation.name,'Organisation'),
  reportName:value(input.design.projectName,'Power BI Report'),purpose:value(input.design.overview||input.interpretation.objective),audience:value(input.design.audience||input.interpretation.audience),
  businessQuestions:list(input.interpretation.businessQuestions),kpis:list(input.design.measures.map(item=>item.name).length?input.design.measures.map(item=>item.name):input.interpretation.kpis),
  projectName:value(input.candidate.projectName),semanticModel:`${value(input.candidate.projectName)}.SemanticModel`,report:`${value(input.candidate.projectName)}.Report`,
  pages:input.design.pages.map(page=>({name:value(page.name),purpose:value(page.purpose),visuals:page.visuals.map(visual=>`${value(visual.title)} (${value(visual.type)})`)})),
  measures:list(input.design.measures.map(item=>item.name)),visualTypes:[...new Set(input.design.pages.flatMap(page=>page.visuals.map(visual=>visual.type)))],
  sourceFormat:input.data.format,sourceFile:value(input.data.fileName),tables:input.data.tables.map(table=>({name:value(table.sourceName||table.name),columns:table.columns.map(column=>value(column.sourceName||column.name))})),
  relationships:input.data.relationships.map(item=>`${value(item.fromTable)}.${value(item.fromColumn)} to ${value(item.toTable)}.${value(item.toColumn)} (${value(item.cardinality)})`),prototypeSource:true,
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
 const checklist=['PBIP opens successfully in a supported Power BI Desktop version','Semantic model loads','Expected tables and relationships are present','Key measures return sensible results','Report pages render without visual errors','Slicers, filters and navigation operate correctly','Production connection is configured','Credentials are configured securely','Gateway requirement is resolved','Data refresh succeeds',model.rlsRequirements.length?'RLS is tested using appropriate personas':'No RLS configuration is required','Target workspace is confirmed','Published report is validated','Business owner validates KPI definitions and results'];
 const requiredActions=['Replace the request-specific prototype input with the approved production source.','Configure the production data connection and credentials.','Open and validate the PBIP candidate in Power BI Desktop.','Confirm publishing permissions for the target Power BI or Fabric workspace.','Complete a successful refresh before release.',...(model.rlsRequirements.length?['Map the generated RLS requirements to approved users or groups and test them with appropriate personas.']:[])];
 const notApplicableActions=model.rlsRequirements.length?[]:['RLS configuration is not applicable to this candidate because the Report Design contains no RLS requirement.'];
 const undeterminedActions=['Gateway requirement: To be confirmed.','Target workspace: To be confirmed.','Refresh schedule: To be confirmed.','Production source endpoint and environment-specific parameters: To be confirmed.'];
 const content:Content[]=[
  {canvas:[{type:'rect',x:0,y:0,w:515,h:7,color:model.primaryColour}],margin:[0,0,0,12]},
  {text:model.organisation.toUpperCase(),fontSize:9,bold:true,color:model.accentColour,characterSpacing:1},
  {text:'POWER BI REPORT DEPLOYMENT & HANDOVER GUIDE',style:'title'},
  {text:model.reportName,style:'subtitle'},
  table([['Document metadata','Value'],['Generated',generatedLabel],['Run reference',model.runId],['Application version',model.applicationVersion],['Validation',model.validationOutcome],['Tenant theme',model.themeName]],['auto','*']),
  section('Report summary',[{text:model.purpose},{text:'Intended audience',style:'minorHeading'},{text:model.audience},{text:'Business questions and outcomes',style:'minorHeading'},bullets(model.businessQuestions),{text:'Key measures',style:'minorHeading'},bullets(model.kpis),{text:'Generated pages',style:'minorHeading'},bullets(model.pages.map(page=>`${page.name}: ${page.purpose}`))]),
  section('What APBRA generated',[table([['Generated component','Current candidate'],['PBIP project',model.projectName],['Report',model.report],['Semantic model',model.semanticModel],['Pages',model.pages.map(page=>page.name).join(', ')||'None'],['Measures',model.measures.join(', ')||'None'],['Visual types',model.visualTypes.join(', ')||'None'],['Deterministic validation',model.validationOutcome]],['auto','*'])]),
  section('Data structure and source summary',[{text:`${model.sourceFormat} schema/data used to generate the candidate: ${model.sourceFile}. The uploaded content is request-specific prototype input.`},table([['Detected table','Important columns'],...model.tables.map(item=>[item.name,item.columns.join(', ')||'None detected'])],['auto','*']),{text:'Detected relationships',style:'minorHeading'},bullets(model.relationships),{text:'Production data connection',style:'minorHeading'},{text:`The candidate currently uses the uploaded ${model.sourceFormat} structure for ${model.tables.map(item=>item.name).join(', ')||'the detected model'}. Configure the approved production source before deployment.`}]),
  section('Before deployment',[{text:'Required for this candidate',style:'minorHeading'},bullets(requiredActions),{text:'Not applicable',style:'minorHeading'},bullets(notApplicableActions,'No deployment action was classified as not applicable.'),{text:'To be confirmed',style:'minorHeading'},bullets(undeterminedActions)]),
  section('Credentials and security',[{text:'Credentials are not stored in the generated package. Configure credentials only through approved Power BI, Fabric or platform settings.'},{text:'Never enter passwords, API keys, access tokens or other secrets into APBRA report requirements. Production permissions and access configuration remain the responsibility of the customer or tenant.',margin:[0,5,0,0]}]),
  section('Opening the generated Power BI project',{ol:['Download the PBIP candidate.','Extract the downloaded ZIP.','Locate the generated .pbip project file.','Open the .pbip project using a compatible Power BI Desktop version.','Review the semantic model and report.','Configure the appropriate production data connection and credentials.','Refresh and validate the report before publishing.']}),
  section('Connection and gateway configuration',[{text:`Detected model requiring production connection mapping: ${model.tables.map(item=>item.name).join(', ')||'To be confirmed'}.`},{text:'Gateway requirement: To be confirmed. After the production connection is configured, verify connectivity with a successful refresh before publishing.',margin:[0,5,0,0]}],true),
  section('Workspace and publishing',{ol:['Select the approved Power BI or Fabric workspace.','Confirm that the publisher has the required workspace permissions.','Publish using the supported Power BI process after Desktop validation.','Confirm that the report and semantic model are present in the target workspace.','Validate intended user access after publishing.']}),
  section('Refresh configuration',[{text:'Configure credentials before refresh and complete one successful refresh test. Refresh schedule: To be confirmed. If a gateway is required after assessment, bind it to the production source and confirm it is online.'}]),
  section('RLS and access',model.rlsRequirements.length?[{text:'The Report Design contains the following RLS requirements:'},bullets(model.rlsRequirements),{text:'Map each requirement to approved deployment-time users or groups and validate access with appropriate test personas. No user or group identity has been invented by APBRA.'}]:[{text:'No RLS requirement was generated for this candidate.'}]),
  section('Post-deployment validation checklist',checklist.map(item=>({text:`[ ] ${item}`,style:'check'}))),
  section('Warnings and known limitations',[bullets(remainingWarnings,'No run-specific warnings or assumptions were recorded.'),{text:'APBRA’s current Power BI compiler supports a bounded subset of Power BI report capabilities. Successful generation does not imply universal Power BI feature compatibility.',margin:[0,5,0,0]}],true),
  section('Changing the report later',[{text:'Update production source or endpoint configuration through approved platform settings. Schema changes, new measures, changed visuals, branding changes, or material requirement changes should trigger a new APBRA generation and validation cycle rather than silently altering an already validated candidate.'}],true),
  {text:'Generation and download of this package do not mean that the report has been deployed to production. Production connection configuration, credentials, workspace publishing, access configuration, refresh validation and business verification remain deployment activities.',style:'callout'},
 ];
 return{pageSize:'A4',pageMargins:[40,52,40,48],info:{title:`${model.reportName} - Deployment Guide`,author:model.organisation,subject:'Power BI report deployment and handover'},defaultStyle:{font:'Roboto',fontSize:9,lineHeight:1.25,color:'#242424'},styles,footer:(page,current)=>({columns:[{text:`APBRA · ${model.runId}`,fontSize:8,color:'#605E5C'},{text:`Page ${page} of ${current}`,alignment:'right',fontSize:8,color:'#605E5C'}],margin:[40,12,40,0]}),content};
}

export async function generateDeploymentGuide(input:DeploymentGuideInput):Promise<DeploymentGuideArtifact>{
 const model=createDeploymentGuideModel(input);const definition=deploymentGuideDocument(model);
 const bytes=await new Promise<Uint8Array<ArrayBuffer>>((resolve,reject)=>{try{pdfMake.createPdf(definition,undefined,undefined,pdfFonts).getBuffer(buffer=>resolve(new Uint8Array(buffer)))}catch(error){reject(error)}});
 if(bytes.length<8||new TextDecoder('latin1').decode(bytes.slice(0,8)).slice(0,5)!=='%PDF-')throw new Error('DEPLOYMENT_GUIDE_PDF_INVALID');
 return{filename:DEPLOYMENT_GUIDE_FILENAME,bytes,model};
}
