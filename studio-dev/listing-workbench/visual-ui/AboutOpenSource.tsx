export default function AboutOpenSource(){
  return <details className="jf-open-source">
    <summary>关于与开源说明</summary>
    <div>
      <p>钧飞工作台的部分视觉编辑组件、生成流程与提示词改编自 <a href="https://github.com/Hector-xue/IvyeaOps" target="_blank" rel="noreferrer">Hector-xue/IvyeaOps</a>，来源版本 <a href="https://github.com/Hector-xue/IvyeaOps/tree/51f5141b475e64b67638f396451d887531caa761" target="_blank" rel="noreferrer">51f5141</a>。组合后的工作台按 AGPL-3.0-only 提供。</p>
      <p>原版权、许可证与本地修改说明保留在对应源码中的 SOURCE-NOTICE.md、visual-ui/NOTICE.md 和 LICENSE-AGPL-3.0.txt。其他开源依赖保留各自许可证。</p>
      <p><a href="/api/studio/source">下载本部署对应源码</a></p>
    </div>
  </details>;
}
