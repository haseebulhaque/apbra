/** Small stored ZIP writer: UTF-8 names, deterministic DOS epoch, no compression.
 * Limits deliberately exclude ZIP64, paths outside the archive and huge inputs. */
export function crc32(bytes:Uint8Array):number {let crc=0xffffffff;for(const b of bytes){crc^=b;for(let j=0;j<8;j++)crc=(crc>>>1)^((crc&1)?0xedb88320:0);}return (crc^0xffffffff)>>>0;}
export function utf8ToBase64(text:string):string {
 const bytes=new TextEncoder().encode(text);let binary='';
 for(let offset=0;offset<bytes.length;offset+=0x8000)binary+=String.fromCharCode(...bytes.subarray(offset,offset+0x8000));
 return btoa(binary);
}
export function zipFiles(files:Record<string,string>):Uint8Array<ArrayBuffer> {
 const encoder=new TextEncoder(),entries=Object.entries(files).sort(([a],[b])=>a.localeCompare(b));
 if(!entries.length||entries.length>1000)throw new Error('ARCHIVE_ENTRY_LIMIT');
 const local:number[]=[],central:number[]=[];
 const append=(to:number[],value:number,size:number)=>{for(let i=0;i<size;i++)to.push((value>>>(8*i))&255);};
 for(const [path,text] of entries){
  if(!/^[A-Za-z0-9_\[\]-][A-Za-z0-9_\[\]./-]*$/.test(path)||path.split('/').some(p=>!p||p==='.'||p==='..'))throw new Error('ARCHIVE_UNSAFE_PATH');
  const name=encoder.encode(path),data=encoder.encode(text),offset=local.length,crc=crc32(data);
  if(name.length>255||data.length>2_000_000||offset+data.length>10_000_000)throw new Error('ARCHIVE_SIZE_LIMIT');
  for(const [value,size] of [[0x04034b50,4],[20,2],[0x800,2],[0,2],[0,2],[33,2],[crc,4],[data.length,4],[data.length,4],[name.length,2],[0,2]])append(local,value,size);
  for(const byte of name)local.push(byte);for(const byte of data)local.push(byte);
  for(const [value,size] of [[0x02014b50,4],[20,2],[20,2],[0x800,2],[0,2],[0,2],[33,2],[crc,4],[data.length,4],[data.length,4],[name.length,2],[0,2],[0,2],[0,2],[0,2],[0,4],[offset,4]])append(central,value,size);
  for(const byte of name)central.push(byte);
 }
 const end:number[]=[];for(const [v,s] of [[0x06054b50,4],[0,2],[0,2],[entries.length,2],[entries.length,2],[central.length,4],[local.length,4],[0,2]])append(end,v,s);
 return new Uint8Array([...local,...central,...end]);
}
