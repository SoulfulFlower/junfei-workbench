import { useEffect, useState } from "react";
export type RepairNode = { type: "text" | "tag" | "newLine"; text?: string; placeholder?: string };
export default function RepairTemplateInput({ id, disabled, onChange }: { id: string; disabled: boolean; onChange: (text: string, nodes: RepairNode[]) => void }) {
  const [nodes, setNodes] = useState<RepairNode[]>([]), [error, setError] = useState("");
  useEffect(() => { setNodes([]); setError(""); }, [id]);
  async function load() {
    try {
      const r = await fetch("/api/image-templates/item?kind=repair&id=" + encodeURIComponent(id)); const row = await r.json();
      if (!r.ok) throw new Error(row.error || "模板读取失败");
      const text = String(row.config.prompt || ""), next: RepairNode[] = []; let end = 0;
      for (const match of text.matchAll(/\[([^\]]*)\]/g)) {
        const start = match.index!; if (start > end) next.push({ type: "text", text: text.slice(end, start) });
        next.push({ type: "tag", text: "", placeholder: match[1] }); end = start + match[0].length;
      }
      if (end < text.length) next.push({ type: "text", text: text.slice(end) });
      setNodes(next);
    } catch (e) { setError(String(e)); }
  }
  function update(index: number, value: string) {
    const next = nodes.map((node, i) => i === index ? { ...node, text: value } : node); setNodes(next);
    onChange(next.map(n => n.type === "newLine" ? "\n" : n.text || "").join(""), next);
  }
  return <div className="ie-template-input"><button disabled={disabled} onClick={() => void load()}>按原模板填写要求</button>
    {nodes.map((node, index) => node.type === "tag" ? <label key={index}>{node.placeholder}<input value={node.text || ""} disabled={disabled} placeholder="填写本次真实内容" onChange={e => update(index, e.target.value)} /></label> : <span key={index}>{node.text}</span>)}
    {nodes.length > 0 && <p>示例只作填写提示，空栏不会作为商品事实提交。</p>}{error && <p role="alert">{error}</p>}
  </div>;
}
