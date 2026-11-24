const fs=await import('node:fs/promises');
export const out=process.env.JUNFEI_CYCLIC_OUTPUT;
if(!out)throw new Error('Set JUNFEI_CYCLIC_OUTPUT to this task output directory');
export async function save(name,data){await fs.writeFile(out+'/'+name,JSON.stringify(data,null,2));}
export async function cards(p,limit=16){
 const asins=await p.evaluate(n=>[...document.querySelectorAll('[data-component-type="s-search-result"][data-asin]')].slice(0,n).map(c=>c.dataset.asin),limit);
 for(const asin of asins){await p.evaluate(a=>document.querySelector('[data-component-type="s-search-result"][data-asin="'+a+'"]').scrollIntoView({block:'center'}),asin);try{await p.waitForFunction(a=>document.querySelector('[data-component-type="s-search-result"][data-asin="'+a+'"]')?.innerText.includes('品牌:'),asin,{timeout:1800})}catch{}}
 return await p.evaluate(n=>({url:location.href,checkedAt:new Date().toISOString(),sort:document.querySelector('#s-result-sort-select')?.value,products:[...document.querySelectorAll('[data-component-type="s-search-result"][data-asin]')].slice(0,n).map(c=>{const raw=c.innerText;return {asin:c.dataset.asin,title:c.querySelector('h2')?.innerText,image:c.querySelector('img.s-image')?.src,price:c.querySelector('.a-price .a-offscreen')?.textContent,brand:raw.match(/品牌:\s*([^\n]+)/)?.[1]?.trim(),date:raw.match(/上架时间:\s*(\d{4}-\d{2}-\d{2})/)?.[1],sellerName:raw.match(/卖家:\s*([^\n]+)/)?.[1]?.trim(),ranks:[...raw.matchAll(/#([\d,]+)\s*\nin\s*([^\n]+)/g)].map(m=>({value:Number(m[1].replaceAll(',','')),category:m[2]})),raw}}),next:document.querySelector('a.s-pagination-next')?.href}),limit);
}
export async function detail(p,asin){const url='https://www.amazon.com/dp/'+asin;
 try{await p.goto(url,{waitUntil:'domcontentloaded',timeout:25000})}catch(e){if(!String(e).includes('navigation committed at')||!(await p.url()).startsWith(url))throw e;}
 await p.waitForSelector('#productTitle',{state:'visible',timeout:15000});
 const d=await p.evaluate(()=>({url:location.href,checkedAt:new Date().toISOString(),title:document.querySelector('#productTitle')?.innerText,brand:document.querySelector('#bylineInfo')?.innerText,image:document.querySelector('#landingImage')?.src,features:document.querySelector('#feature-bullets')?.innerText,text:document.body.innerText.slice(0,30000),sellerLinks:[...document.querySelectorAll('a[href*="seller="]')].map(a=>({text:a.innerText,url:a.href})),dateElements:[...document.querySelectorAll('[id*="seller-sprite"],[id*="sellersprite"],[class*="sellersprite"]')].filter(n=>n.innerText?.includes('上架时间')).map(n=>({id:n.id,class:n.className,text:n.innerText.slice(0,9000)})).slice(0,6)}));
 await save('detail-'+asin+'.json',d);return d;
}
