export type TenantSettings={
  organisation:{name:string;displayName:string;locale:string;timezone:string};
  ai:{provider:'Azure AI Foundry';authentication:'API key'|'Entra ID'};
  rag:{enabled:boolean;topK:number;chunkTargetTokens:number;overlapStrategy:string;indexType:string;strategy:string};
  governance:{requireKnowledge:boolean;requireAccessibility:boolean;requireValidation:boolean;maxVisualsPerPage:number;maxPages:number;humanReviewAtVisuals:number};
  generation:{enabled:boolean;supportedCapabilities:string[];validationRequired:boolean;policy:string};
  branding:{primary:string;accent:string;reportNaming:string;pageNaming:string;executiveConvention:string;themeName:string};
};

export const defaultTenantSettings:TenantSettings={
  organisation:{name:'Contoso Analytics',displayName:'Contoso Power BI Automation',locale:'en-AU',timezone:'Australia/Sydney'},
  ai:{provider:'Azure AI Foundry',authentication:'API key'},
  rag:{enabled:true,topK:4,chunkTargetTokens:500,overlapStrategy:'Heading-aware; overlap only when a section is split',indexType:'In-memory exact cosine index',strategy:'Heading-aware and token-aware policy chunks'},
  governance:{requireKnowledge:true,requireAccessibility:true,requireValidation:true,maxVisualsPerPage:20,maxPages:5,humanReviewAtVisuals:15},
  generation:{enabled:true,supportedCapabilities:['KPI cards','Bar and column charts','Line charts','Tables','Slicers','Multiple pages','Explicit measures','Simple star-schema relationships','Theme colours'],validationRequired:true,policy:'Compile supported designs; route unsupported capabilities to human review.'},
  branding:{primary:'#005A9C',accent:'#2D7D9A',reportNaming:'PascalCase project names',pageNaming:'Short audience-oriented page names',executiveConvention:'Headline KPIs first; focused pages; clear filters',themeName:'Contoso Executive'},
};
