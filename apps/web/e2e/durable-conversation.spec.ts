import {expect,test,type Page} from '@playwright/test';

async function signIn(page:Page){
  await page.goto('/');
  await page.getByText('Local development identities').click();
  await page.getByRole('link',{name:'member',exact:true}).click();
}

async function expectSyntheticUploadPolicy(page:Page){
  await expect(page.getByText('CSV, XLSX data · PNG, JPEG, JPG reference · up to 8 at once')).toBeVisible();
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
  await page.getByRole('button',{name:'Create report'}).first().click();
  const request='Help managers understand the supplied fleet evidence.';
  await page.getByLabel('Your reporting goal').fill(request);
  await page.locator('.new-report-card').getByRole('button',{name:/Create report/}).click();
  await expect(page.getByText('Report request created and saved.')).toBeVisible();

  const message='Use monthly periods and keep maintenance class available for filtering.';
  await page.getByLabel('Add more requirements').fill(message);
  const savedMessage=page.waitForResponse(response=>response.url().endsWith('/conversation')&&response.request().method()==='POST');
  await page.getByRole('button',{name:'Add to report requirements'}).click();
  expect((await savedMessage).status()).toBe(200);
  await expect(page.getByLabel('Add more requirements')).toBeEmpty();
  await expect(page.getByText(message,{exact:true})).toBeVisible();

  await expectSyntheticUploadPolicy(page);
  await page.locator('input[type=file]').setInputFiles([
    {name:'fleet.csv',mimeType:'text/csv',buffer:Buffer.from('Date,Depot,Availability\n2026-01-01,North,0.96\n')},
    {name:'layout.png',mimeType:'image/png',buffer:Buffer.concat([Buffer.from([0x89,0x50,0x4e,0x47,0x0d,0x0a,0x1a,0x0a]),Buffer.from('synthetic reference')])},
  ]);
  await page.getByRole('button',{name:'Add selected files'}).click();
  await expect(page.locator('.evidence-attached')).toContainText('2 saved');
  await expect(page.getByText(/Data source.*CSV/)).toBeVisible();
  await expect(page.getByText('Saved, visual meaning not interpreted')).toBeVisible();
  await page.getByText('Source details').click();
  await expect(page.getByText(/Depot \(text\).*Availability \(decimal\)/)).toBeVisible();
  await page.getByRole('button',{name:'Review my requirements'}).click();
  await expect(page.getByText('One point needs your input',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:/Summarise Availability and compare it by Depot/}).click();
  await expect(page.getByText('APBRA used the complete current report context and qualified data fields. Review the business meaning before confirming it.')).toBeVisible();
  await page.getByRole('button',{name:'Confirm report requirements'}).click();
  await expect(page.getByText('Your report requirements are confirmed')).toBeVisible();

  await page.reload();
  await page.getByRole('button',{name:new RegExp(request)}).first().click();
  await expect(page.getByText(message,{exact:true})).toBeVisible();
  await expect(page.locator('.evidence-attached')).toContainText('2 saved');
  await expect(page.getByText(/Data source.*CSV/)).toBeVisible();
  await expect(page.getByText('Saved, visual meaning not interpreted')).toBeVisible();
  await expect(page.getByText('Your report requirements are confirmed')).toBeVisible();
  await page.getByLabel('Current business request').fill('Compare synthetic fleet availability by depot and maintenance class.');
  await page.getByRole('button',{name:'Save new version'}).click();
  await expect(page.getByText(/Reconfirmation required/)).toBeVisible();
});

test('protected XLSX evidence follows the same deterministic confirmation path',async({page})=>{
  await signIn(page);
  await page.getByRole('button',{name:'Create report'}).first().click();
  const request='Compare WaitMinutes by Clinic for appointment operations.';
  await page.getByLabel('Your reporting goal').fill(request);
  await page.locator('.new-report-card').getByRole('button',{name:/Create report/}).click();
  await expectSyntheticUploadPolicy(page);
  const workbook=supportedXlsx();
  await page.locator('input[type=file]').setInputFiles({name:'appointments.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:workbook});
  await page.getByRole('button',{name:'Add selected files'}).click();
  await expect(page.locator('.evidence-attached')).toContainText('1 saved');
  await expect(page.getByText(/Data source.*XLSX/)).toBeVisible();
  await page.getByText('Source details').click();
  await expect(page.getByText(/Clinic \(text\).*WaitMinutes \(integer\)/)).toBeVisible();
  await page.getByRole('button',{name:'Review my requirements'}).click();
  await expect(page.getByText('APBRA used the complete current report context and qualified data fields. Review the business meaning before confirming it.')).toBeVisible();
  await page.getByRole('button',{name:'Confirm report requirements'}).click();
  await expect(page.getByText('Your report requirements are confirmed')).toBeVisible();
  await page.reload();
  await page.getByRole('button',{name:new RegExp(request)}).first().click();
  await expect(page.locator('.evidence-attached')).toContainText('1 saved');
  await expect(page.getByText(/Data source.*XLSX/)).toBeVisible();
  await expect(page.getByText('Your report requirements are confirmed')).toBeVisible();
});

test('a late interpretation response cannot repaint a newer request as current',async({page})=>{
  await signIn(page);
  await page.getByRole('button',{name:'Create report'}).first().click();
  await page.getByLabel('Your reporting goal').fill('Compare Availability by Depot.');
  await page.locator('.new-report-card').getByRole('button',{name:/Create report/}).click();
  await expectSyntheticUploadPolicy(page);
  await page.locator('input[type=file]').setInputFiles({
    name:'availability.csv',
    mimeType:'text/csv',
    buffer:Buffer.from('Depot,Availability\nNorth,0.96\n'),
  });
  await page.getByRole('button',{name:'Add selected files'}).click();

  let release!:()=>void,observed!:()=>void;
  const held=new Promise<void>(resolve=>{release=resolve});
  const intercepted=new Promise<void>(resolve=>{observed=resolve});
  await page.route('**/api/cases/*/interpretations',async route=>{
    observed();
    await held;
    await route.continue();
  });
  await page.getByRole('button',{name:'Review my requirements'}).click();
  await intercepted;
  await page.getByLabel('Current business request').fill(
    'Compare the revised maintenance schedule by facility.',
  );
  await page.getByRole('button',{name:'Save new version'}).click();
  await expect(page.getByText('Your updated request was saved.')).toBeVisible();
  release();
  await expect(page.getByText('This local preview uses deterministic rules to propose an understanding; no AI model was called.')).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Review my requirements'})).toBeDisabled();
});
