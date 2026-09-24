import {expect,test,type Page} from '@playwright/test';

async function signIn(page:Page){
  await page.goto('/');
  await page.getByText('Local development identities').click();
  await page.getByRole('link',{name:'member',exact:true}).click();
}

function crc32(data:Buffer){let value=0xffffffff;for(const byte of data){value^=byte;for(let bit=0;bit<8;bit+=1)value=(value>>>1)^((value&1)?0xedb88320:0)}return(value^0xffffffff)>>>0}
function storedZip(entries:Array<[string,string]>){const local:Buffer[]=[],central:Buffer[]=[];let offset=0;for(const[name,text]of entries){const filename=Buffer.from(name),data=Buffer.from(text),crc=crc32(data),header=Buffer.alloc(30),directory=Buffer.alloc(46);header.writeUInt32LE(0x04034b50,0);header.writeUInt16LE(20,4);header.writeUInt32LE(crc,14);header.writeUInt32LE(data.length,18);header.writeUInt32LE(data.length,22);header.writeUInt16LE(filename.length,26);directory.writeUInt32LE(0x02014b50,0);directory.writeUInt16LE(20,4);directory.writeUInt16LE(20,6);directory.writeUInt32LE(crc,16);directory.writeUInt32LE(data.length,20);directory.writeUInt32LE(data.length,24);directory.writeUInt16LE(filename.length,28);directory.writeUInt32LE(offset,42);local.push(header,filename,data);central.push(directory,filename);offset+=header.length+filename.length+data.length}const directoryOffset=offset,directoryBytes=Buffer.concat(central),end=Buffer.alloc(22);end.writeUInt32LE(0x06054b50,0);end.writeUInt16LE(entries.length,8);end.writeUInt16LE(entries.length,10);end.writeUInt32LE(directoryBytes.length,12);end.writeUInt32LE(directoryOffset,16);return Buffer.concat([...local,directoryBytes,end])}
function supportedXlsx(){return storedZip([
  ['xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Observations" sheetId="1" r:id="rId1"/></sheets></workbook>'],
  ['xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/></Relationships>'],
  ['xl/worksheets/sheet1.xml','<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c t="inlineStr"><is><t>Clinic</t></is></c><c t="inlineStr"><is><t>WaitMinutes</t></is></c></row><row><c t="inlineStr"><is><t>East</t></is></c><c><v>14</v></c></row></sheetData></worksheet>'],
])}

test('saved conversation, qualified CSV evidence, clarification and confirmation survive reload',async({page})=>{
  await signIn(page);
  const request='Help managers understand the supplied fleet evidence.';
  await page.getByLabel('Original business request').fill(request);
  await page.getByRole('button',{name:'Create case'}).click();
  await expect(page.getByText('Reporting case created and saved.')).toBeVisible();

  const message='Use monthly periods and keep maintenance class available for filtering.';
  await page.getByLabel('Add a business message').fill(message);
  await page.getByRole('button',{name:'Save message'}).click();
  await expect(page.getByText(message,{exact:true})).toBeVisible();
  await expect(page.getByText('Context 2',{exact:true})).toBeVisible();

  await page.getByLabel('Add CSV or XLSX evidence').setInputFiles({
    name:'fleet.csv',
    mimeType:'text/csv',
    buffer:Buffer.from('Date,Depot,Availability\n2026-01-01,North,0.96\n'),
  });
  await expect(page.getByText(/fleet\.csv.*CSV/)).toBeVisible();
  await expect(page.getByText('Depot (text), Availability (decimal)')).toBeVisible();
  await page.getByRole('button',{name:'Prepare understanding'}).click();
  await expect(page.getByText('Clarification required',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:/Summarise Availability and compare it by Depot/}).click();
  await expect(page.getByText('Local deterministic interpretation preview — no AI/model call.')).toBeVisible();
  await page.getByRole('button',{name:'Confirm this exact meaning'}).click();
  await expect(page.getByText('ConfirmedRequirementContract v2 created')).toBeVisible();

  await page.reload();
  await page.getByRole('button',{name:new RegExp(request)}).first().click();
  await expect(page.getByText(message,{exact:true})).toBeVisible();
  await expect(page.getByText(/fleet\.csv.*CSV/)).toBeVisible();
  await expect(page.getByText('Qualified evidence · 1')).toBeVisible();
  await expect(page.getByText('ConfirmedRequirementContract v2 created')).toBeVisible();
  await page.getByLabel('Current business request').fill('Compare synthetic fleet availability by depot and maintenance class.');
  await page.getByRole('button',{name:'Save new version'}).click();
  await expect(page.getByText(/Reconfirmation required/)).toBeVisible();
});

test('protected XLSX evidence follows the same deterministic confirmation path',async({page})=>{
  await signIn(page);
  const request='Compare WaitMinutes by Clinic for appointment operations.';
  await page.getByLabel('Original business request').fill(request);
  await page.getByRole('button',{name:'Create case'}).click();
  const workbook=supportedXlsx();
  await page.getByLabel('Add CSV or XLSX evidence').setInputFiles({name:'appointments.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:workbook});
  await expect(page.getByText(/appointments\.xlsx.*XLSX/)).toBeVisible();
  await expect(page.getByText('Clinic (text), WaitMinutes (integer)')).toBeVisible();
  await page.getByRole('button',{name:'Prepare understanding'}).click();
  await expect(page.getByText('Local deterministic interpretation preview — no AI/model call.')).toBeVisible();
  await page.getByRole('button',{name:'Confirm this exact meaning'}).click();
  await expect(page.getByText('ConfirmedRequirementContract v2 created')).toBeVisible();
  await page.reload();
  await page.getByRole('button',{name:new RegExp(request)}).first().click();
  await expect(page.getByText(/appointments\.xlsx.*XLSX/)).toBeVisible();
  await expect(page.getByText('ConfirmedRequirementContract v2 created')).toBeVisible();
});

test('a late interpretation response cannot repaint a newer request as current',async({page})=>{
  await signIn(page);
  await page.getByLabel('Original business request').fill('Compare Availability by Depot.');
  await page.getByRole('button',{name:'Create case'}).click();
  await page.getByLabel('Add CSV or XLSX evidence').setInputFiles({
    name:'availability.csv',
    mimeType:'text/csv',
    buffer:Buffer.from('Depot,Availability\nNorth,0.96\n'),
  });

  let release!:()=>void,observed!:()=>void;
  const held=new Promise<void>(resolve=>{release=resolve});
  const intercepted=new Promise<void>(resolve=>{observed=resolve});
  await page.route('**/api/cases/*/interpretations',async route=>{
    observed();
    await held;
    await route.continue();
  });
  await page.getByRole('button',{name:'Prepare understanding'}).click();
  await intercepted;
  await page.getByLabel('Current business request').fill(
    'Compare the revised maintenance schedule by facility.',
  );
  await page.getByRole('button',{name:'Save new version'}).click();
  await expect(page.getByText('A new immutable request version was saved.')).toBeVisible();
  release();
  await expect(page.getByText('Local deterministic interpretation preview — no AI/model call.')).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Prepare understanding'})).toBeDisabled();
});
