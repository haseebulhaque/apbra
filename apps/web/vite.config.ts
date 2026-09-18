import {defineConfig,loadEnv,type Plugin} from 'vite';
import type {IncomingMessage,ServerResponse} from 'node:http';

function azureAdapter(env:Record<string,string>):Plugin{
  const endpoint=(env.AZURE_AI_ENDPOINT||'').replace(/\/$/,'');
  const chat=env.AZURE_AI_CHAT_DEPLOYMENT||'';
  const embedding=env.AZURE_AI_EMBEDDING_DEPLOYMENT||'';
  const key=env.AZURE_AI_API_KEY||'';
  const version=env.AZURE_AI_API_VERSION||'';
  const authentication=(env.AZURE_AI_AUTH_METHOD||'api_key').toLowerCase()==='entra'?'Entra ID':'API key';
  const v1=/\/openai\/v1$/i.test(endpoint);
  const configured=Boolean(endpoint&&chat&&embedding&&key);
  let endpointDisplay='Not configured';try{const url=new URL(endpoint);const prefix=url.hostname.slice(0,4);endpointDisplay=`${url.protocol}//${prefix}••••${url.hostname.slice(-18)}${url.pathname}`}catch{}
  const route=(kind:'chat'|'embeddings')=>v1?`${endpoint}/${kind==='chat'?'chat/completions':'embeddings'}`:`${endpoint}/openai/deployments/${encodeURIComponent(kind==='chat'?chat:embedding)}/${kind==='chat'?'chat/completions':'embeddings'}?api-version=${encodeURIComponent(version)}`;
  async function handle(req:IncomingMessage,res:ServerResponse,next:()=>void){
    if(req.url==='/api/ai/status'){res.setHeader('Content-Type','application/json');res.end(JSON.stringify({configured,chatDeployment:chat,embeddingDeployment:embedding,apiMode:v1?'openai-v1':'deployment-api-version',endpointDisplay,authentication}));return}
    const kind=req.url==='/api/ai/chat'?'chat':req.url==='/api/ai/embeddings'?'embeddings':null;if(!kind){next();return}
    if(req.method!=='POST'){res.statusCode=405;res.end();return}if(!configured||(!v1&&!version)){res.statusCode=503;res.setHeader('Content-Type','application/json');res.end(JSON.stringify({error:{code:'AI_SERVICE_UNAVAILABLE'}}));return}
    try{let raw='';for await(const part of req){raw+=part;if(raw.length>2_000_000)throw new Error('REQUEST_TOO_LARGE')}const body=JSON.parse(raw);body.model=kind==='chat'?chat:embedding;
      const upstream=await fetch(route(kind),{method:'POST',headers:{'Content-Type':'application/json','api-key':key},body:JSON.stringify(body),signal:AbortSignal.timeout(120000)});const text=await upstream.text();res.statusCode=upstream.status;res.setHeader('Content-Type',upstream.headers.get('content-type')||'application/json');res.end(text);
    }catch(error){res.statusCode=502;res.setHeader('Content-Type','application/json');res.end(JSON.stringify({error:{code:error instanceof Error?error.message:'AI_SERVICE_UNAVAILABLE'}}));}
  }
  return {name:'local-azure-ai-adapter',configureServer(server){server.middlewares.use(handle)},configurePreviewServer(server){server.middlewares.use(handle)}};
}
export default defineConfig(({mode})=>{const env=loadEnv(mode,process.cwd(),'AZURE_AI_');return {plugins:[azureAdapter(env)]}});
