import {Component,type ReactNode} from 'react';

// A visual record or a failed module must not remove the whole product editor.
export default class WorkspaceBoundary extends Component<{children:ReactNode},{error:string;attempt:number}> {
  state={error:'',attempt:0};
  static getDerivedStateFromError(error:Error){return {error:error.message||'页面加载异常'};}
  render(){
    if(this.state.error)return <section className="pe-card" role="alert">
      <h2>视觉套图暂时无法显示</h2><p>{this.state.error}</p>
      <p>已有分镜、图片和后台任务保留。重新加载只读取记录，不会重新生图。</p>
      <button onClick={()=>this.setState(({attempt})=>({error:'',attempt:attempt+1}))}>重新加载视觉套图</button>
    </section>;
    return <div key={this.state.attempt}>{this.props.children}</div>;
  }
}
