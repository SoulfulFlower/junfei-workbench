const fs=await import('node:fs/promises');
const {out,save}=await import('./cyclic_browser_helpers.mjs');
function jsonAt(s,start){let depth=0,quoted=false,escape=false;for(let i=start;i<s.length;i++){const c=s[i];if(quoted){if(escape)escape=false;else if(c==='\\')escape=true;else if(c==='"')quoted=false;continue;}if(c==='"')quoted=true;else if(c==='{'||c==='[')depth++;else if(c==='}'||c===']'){depth--;if(depth===0)return JSON.parse(s.slice(start,i+1));}}throw Error('Incomplete image JSON');}
export function parseImages(data){const all=[],colorImages={};for(const s of data.scripts){const m=s.match(/"colorImages"\s*:\s*\{/);if(m){Object.assign(colorImages,jsonAt(s,m.index+m[0].length-1));}const re=/parseJSON\('\s*\[/g;for(const match of s.matchAll(re)){try{const a=jsonAt(s,match.index+match[0].length-1);if(a.some(x=>x.hiRes||x.large))all.push(...a);}catch{}}}return {gallery:all,colorImages};}
export async function collectFamilyImages(task,asin,colors){
 const p=task.page('p3'),capture=JSON.parse(await fs.readFile(out+'/full-variants-'+asin+'-parsed.json','utf8')),fields=capture.fields,dimensions=fields.dimensions[0],mapping=fields.dimensionValuesDisplayData[0],ci=dimensions.indexOf('color_name'),si=dimensions.indexOf('size_name');
 const file='collected-images-'+asin+'.json';let prior;try{prior=JSON.parse(await fs.readFile(out+'/'+file,'utf8'))}catch{prior={asin,colors:[],purpose:'collected_reference_images_not_production_assets'};}
 for(const color of colors){if(prior.colors.some(x=>x.color===color&&x.gallery.length))continue;const candidates=Object.entries(mapping).filter(([,v])=>v[ci]===color),chosen=candidates.find(([,v])=>v[si]==='Medium')||candidates[0];if(!chosen)throw Error('Unobserved color '+color);
  const child=chosen[0],url='https://www.amazon.com/dp/'+child;
  try{await p.goto(url,{waitUntil:'domcontentloaded',timeout:25000})}catch(e){if(!(await p.url()).startsWith(url))throw e;}
  await p.waitForSelector('#landingImage',{timeout:15000});const raw=await p.evaluate(()=>({url:location.href,checkedAt:new Date().toISOString(),title:document.querySelector('#productTitle')?.innerText,image:document.querySelector('#landingImage')?.src,hires:document.querySelector('#landingImage')?.getAttribute('data-old-hires'),scripts:[...document.scripts].filter(s=>/colorImages|imageGalleryData/.test(s.textContent)).map(s=>s.textContent)}));
  await save('image-page-'+child+'-raw.json',raw);const images=parseImages(raw),list=images.gallery.length?images.gallery:images.colorImages[color]||[];const gallery=[...new Set(list.map(x=>x.hiRes||x.large).filter(Boolean))];if(!gallery.length)throw Error('No gallery '+child);
  prior.colors.push({color,asin:child,url:raw.url,checkedAt:raw.checkedAt,gallery,rawEvidence:'image-page-'+child+'-raw.json'});await save(file,prior);console.log('CAPTURED_IMAGES',{asin,color,child,images:gallery.length});
 }
 return prior;
}
