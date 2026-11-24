/** Independent pure-JS reconstruction of LinkFox's CPU curve LUT.
 * Evidence: ascent WASM functions502/1137, differential oracle results alongside.
 * GPU texture sampling and mask mixing are outside this module.
 */
export const IDENTITY_CURVE=Object.freeze([[0,0],[255,255]]);
const clamp=x=>Math.min(255,Math.max(0,x));

export function normalizeCurve(points) {
  if(!Array.isArray(points)||points.length<2||points.length>256)throw new RangeError('Expected 2..256 control points');
  const normalized=points.map(p=>{
    if(!Array.isArray(p)||p.length!==2||p.some(x=>typeof x!=='number'||!Number.isFinite(x)||x<0||x>255))throw new RangeError('Expected finite [x,y] control points in 0..255');
    return p.map(Math.fround);
  });
  for(let i=1;i<normalized.length;i++)if(normalized[i][0]<=normalized[i-1][0])throw new RangeError('Control-point x coordinates must remain strictly increasing after float32 conversion');
  // Native code allocates its sample range from integer x coordinates.
  if(Math.trunc(normalized.at(-1)[0])<=Math.trunc(normalized[0][0]))throw new RangeError('Control-point range must span at least one integer sample');
  return normalized;
}

export function nativeCompatibleCurveDoubles(points) {
  const curve=normalizeCurve(points),n=curve.length;
  const xs=curve.map(p=>p[0]),ys=curve.map(p=>p[1]);
  const first=Math.trunc(xs[0]),last=Math.trunc(xs[n-1]);
  const out=new Float64Array(256);
  if(n===2) {
    // Original two-point branch quantizes BOTH coordinates to int32 first.
    const y0=Math.trunc(ys[0]),y1=Math.trunc(ys[1]),slope=(y1-y0)/(last-first);
    for(let i=0;i<256;i++)out[i]=i<first?y0:i>=last?y1:clamp(slope*(i-first)+y0);
    return out;
  }
  // Natural cubic spline with zero second derivative at both endpoints.
  const a=new Float64Array(n),b=new Float64Array(n),c=new Float64Array(n),rhs=new Float64Array(n);
  b[0]=b[n-1]=1;
  for(let i=1;i<n-1;i++) {
    const left=xs[i]-xs[i-1],right=xs[i+1]-xs[i];
    a[i]=left;b[i]=2*(left+right);c[i]=right;
    rhs[i]=6*((ys[i+1]-ys[i])/right-(ys[i]-ys[i-1])/left);
  }
  for(let i=1;i<n;i++) {
    const scale=a[i]/b[i-1];b[i]-=scale*c[i-1];rhs[i]-=scale*rhs[i-1];
  }
  const second=new Float64Array(n);second[n-1]=rhs[n-1]/b[n-1];
  for(let i=n-2;i>=0;i--)second[i]=(rhs[i]-c[i]*second[i+1])/b[i];
  for(let i=0;i<256;i++) {
    if(i<first){out[i]=Math.trunc(ys[0]);continue;}
    if(i>=last){out[i]=Math.trunc(ys[n-1]);continue;}
    // Preserve observed original offset: the interior temporary samples start
    // at zero, and the output accesses them at i-first rather than i.
    const x=i-first;
    let segment=0;while(segment<n-2&&x>xs[segment+1])segment++;
    const h=xs[segment+1]-xs[segment],left=(xs[segment+1]-x)/h,right=(x-xs[segment])/h;
    const value=left*ys[segment]+right*ys[segment+1]+((left*left*left-left)*second[segment]+(right*right*right-right)*second[segment+1])*h*h/6;
    out[i]=clamp(value);
  }
  return out;
}

export function nativeCompatibleCurves(entry={}) {
  const master=nativeCompatibleCurveDoubles(entry.RGB??IDENTITY_CURVE);
  const channels=['R','G','B'].map(name=>{
    const channel=nativeCompatibleCurveDoubles(entry[name]??IDENTITY_CURVE),bytes=new Uint8Array(256);
    for(let i=0;i<256;i++)bytes[i]=Math.trunc(Math.fround(master[Math.trunc(Math.fround(channel[i]))]));
    return bytes;
  });
  const rgba=new Uint8Array(3072);
  for(let c=0;c<3;c++)for(let i=0;i<256;i++)rgba.set([channels[c][i],channels[c][i],channels[c][i],255],c*1024+i*4);
  return {channels,rgba};
}
