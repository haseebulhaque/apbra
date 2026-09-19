import React from 'react';

export type StageState='completed'|'current'|'waiting'|'attention';
export type Tone='neutral'|'success'|'warning'|'danger'|'info';

export function NavItem({active,label,icon,onClick}:{active:boolean;label:string;icon:string;onClick:()=>void}){
  return <button className={`nav-item${active?' nav-active':''}`} aria-current={active?'page':undefined} onClick={onClick}>
    <span className="nav-icon" aria-hidden="true">{icon}</span><span>{label}</span>
  </button>;
}

export function WorkflowStepper({stages}:{stages:Array<{label:string;state:StageState}>}){
  return <ol className="workflow-stepper" aria-label="Report creation progress">
    {stages.map((stage,index)=><li key={stage.label} className={`workflow-stage stage-${stage.state}`} aria-current={stage.state==='current'?'step':undefined}>
      <span className="stage-marker" aria-hidden="true">{stage.state==='completed'?'✓':stage.state==='attention'?'!':index+1}</span>
      <span><strong>{stage.label}</strong><small>{stage.state==='completed'?'Completed':stage.state==='current'?'Current':stage.state==='attention'?'Needs attention':'Waiting'}</small></span>
    </li>)}
  </ol>;
}

export function StatusBadge({tone='neutral',children}:{tone?:Tone;children:React.ReactNode}){
  return <span className={`status-badge status-${tone}`}>{children}</span>;
}

export function SectionHeading({title,description,aside}:{title:string;description?:string;aside?:React.ReactNode}){
  return <div className="section-heading"><div><h2>{title}</h2>{description&&<p>{description}</p>}</div>{aside&&<div className="section-aside">{aside}</div>}</div>;
}

export function DisclosurePanel({summary,children,className='' }:{summary:string;children:React.ReactNode;className?:string}){
  return <details className={`disclosure ${className}`}><summary>{summary}</summary><div className="disclosure-body">{children}</div></details>;
}

export function ProcessingState({title,description}:{title:string;description?:string}){
  return <div className="processing-state" role="status" aria-live="polite"><span className="processing-spinner" aria-hidden="true"/><div><strong>{title}</strong>{description&&<p>{description}</p>}</div></div>;
}

export function EmptyState({title,description,icon='○'}:{title:string;description:string;icon?:string}){
  return <div className="empty-state"><span className="empty-icon" aria-hidden="true">{icon}</span><h2>{title}</h2><p>{description}</p></div>;
}

export function SummaryGroup({label,children,className='' }:{label:string;children:React.ReactNode;className?:string}){
  return <div className={`summary-group ${className}`}><h3>{label}</h3><div>{children}</div></div>;
}

export function FileDownloadRow({title,description,meta,href,filename,label,primary=false}:{title:string;description:string;meta?:string;href:string;filename:string;label:string;primary?:boolean}){
  return <div className="file-row"><span className="file-icon" aria-hidden="true">{title.includes('Power BI')?'PB':'PDF'}</span><div className="file-details"><strong>{title}</strong><p>{description}</p>{meta&&<small>{meta}</small>}</div><a className={primary?'button-link primary-link':'button-link secondary-link'} href={href} download={filename}>{label}</a></div>;
}

export function Callout({tone='info',title,children}:{tone?:Tone;title:string;children:React.ReactNode}){
  return <div className={`callout callout-${tone}`} role={tone==='danger'?'alert':undefined}><div className="callout-symbol" aria-hidden="true">{tone==='success'?'✓':tone==='warning'?'!':tone==='danger'?'×':'i'}</div><div><strong>{title}</strong><div className="callout-content">{children}</div></div></div>;
}

export function TagList({items,empty='To be confirmed'}:{items:string[];empty?:string}){
  return items.length?<div className="tag-list">{items.map(item=><span key={item}>{item}</span>)}</div>:<p className="muted">{empty}</p>;
}
