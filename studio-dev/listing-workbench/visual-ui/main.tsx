import {createRoot,Root} from 'react-dom/client';
import VisualStep from './VisualStep';
import AboutOpenSource from './AboutOpenSource';
import {ToastProvider,useToast} from './toast';
import {useBridge,BridgeContext} from './bridge';
import './visual-original.css';
import './listing.css';
import './theme.css';
import './ProductEditor';
import WorkspaceBoundary from './WorkspaceBoundary';
let root:Root|null=null;
let container:HTMLElement|null=null;
function Studio({context}:{context:BridgeContext}){const notify=useToast(),state=useBridge(context,notify);return <div className="junfei-visual-root">
  {state.loading&&<p role="status">正在读取已保存的分镜和图片…</p>}
  {state.loadError&&<section role="alert"><p>视觉记录读取失败：{state.loadError}</p><button onClick={()=>void state.retryView()}>重新读取</button></section>}
  <VisualStep state={state}/><footer className="jf-attribution"><AboutOpenSource/><p>图片结果需人工核实，AI质检不构成合规保证。</p></footer></div>}
window.JunfeiVisual={mount(element,context){if(container!==element){root?.unmount();container=element;root=createRoot(element);}root!.render(<WorkspaceBoundary key={context.productId}><ToastProvider><Studio context={context}/></ToastProvider></WorkspaceBoundary>);},unmount(){root?.unmount();root=null;container=null;}};
