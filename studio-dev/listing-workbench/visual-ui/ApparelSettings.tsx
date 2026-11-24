export type ApparelConfig = {
  counts: Record<"white" | "model" | "ins" | "seller" | "size", number>;
  consistency: { modelReference?: string; sceneReference?: string; exactScene?: boolean; instructions?: string };
  templatePolicy?: "point-only-v1";
  pointTemplateIds?: string[];
  useLifestyleTemplates?: boolean;
  lifestyleTemplateIds?: string[];
  artDirection?: "legacy-v1" | "template-led-v1";
  sizeChartStyle?: "editorial-split-v1" | "classic-v1";
};

export function defaultApparelConfig(): ApparelConfig {
  return { counts: { white: 1, model: 0, ins: 3, seller: 2, size: 1 }, consistency: {}, templatePolicy: "point-only-v1", pointTemplateIds: [], useLifestyleTemplates: true, lifestyleTemplateIds: [], artDirection: "template-led-v1", sizeChartStyle: "editorial-split-v1" };
}

export function apparelShotOrder(counts: ApparelConfig["counts"]) {
  return (["white", "seller", "model", "ins", "size"] as const).flatMap(kind => Array.from({ length: counts[kind] || 0 }, () => kind));
}

export function ApparelSettings({ value, onChange, upload, disabled, sourcePixelMode = false }: {
  value: ApparelConfig | null; onChange: (value: ApparelConfig | null) => void;
  upload: (file: File) => Promise<string>; disabled: boolean; sourcePixelMode?: boolean;
}) {
  const [error, setError] = useState("");
  async function selectReference(file: File, key: "modelReference" | "sceneReference") {
    if (!value) return;
    try { setError(""); const url = await upload(file); onChange({ ...value, consistency: { ...value.consistency, [key]: url } }); }
    catch (e) { setError(String(e)); }
  }
  return <div className="ie-apparel">
    <label className="ie-check"><input type="checkbox" disabled={disabled} checked={!!value} onChange={e => onChange(e.target.checked ? defaultApparelConfig() : null)} />按服装图种制作</label>
    {!value && <p>可自由选模板逐张创作；需要白底、种草和卖点等独立图种时开启此项。</p>}
    {value && <>
      <p>{sourcePixelMode ? "原片锁定保留原拍摄姿态；需要重新设计商品摄影时，先关闭原片锁定。" : "先分析所选原模板的主体、配图、细节栏与文字层级，再生成画面；无字时保留图片分组。商品结构与真实颜色仍需检查。"}</p>
      <div className="ie-counts">{([["white", "白底图"], ["model", "同模特图"], ["ins", "种草图"], ["seller", "细节图"], ["size", "尺码图"]] as const).map(([key, name]) => <label key={key}>{name}<input aria-label={name + "数量"} type="number" min="0" max="8" disabled={disabled || ((key === "seller" && !!value.pointTemplateIds?.length) || (key === "ins" && !!value.lifestyleTemplateIds?.length))} value={value.counts[key]} onChange={e => onChange({ ...value, counts: { ...value.counts, [key]: Number(e.target.value) } })} /></label>)}</div>
      <p>默认七图：白底主图1张、细节图2张、种草图3张、尺码图1张。所有变体共用第7张尺码图，使用档案真实尺寸数据；缺少依据时停止生成。种草图也使用所选官方原模板，三张的场景、人物形象、姿态和搭配须明显不同，整组独立检查。下方切换细节/种草模板，各自选几种就生成几张；白底与尺码图保持独立。</p>
      {value.counts.size > 0 && <label>尺码图版式<select disabled={disabled} value={value.sizeChartStyle || "editorial-split-v1"} onChange={e => onChange({ ...value, sizeChartStyle: e.target.value as ApparelConfig["sizeChartStyle"] })}><option value="editorial-split-v1">时装目录 · 大商品与清晰表格</option><option value="classic-v1">简洁数据表</option></select></label>}
      {value.counts.model > 0 && <>
        <label>模特参考图{value.consistency.modelReference && <span>已上传</span>}<input type="file" accept="image/png,image/jpeg,image/webp" disabled={disabled} onChange={e => { const file = e.target.files?.[0]; if (file) void selectReference(file, "modelReference"); }} /></label>
        <label>场景参考图{value.consistency.sceneReference && <span>已上传</span>}<input type="file" accept="image/png,image/jpeg,image/webp" disabled={disabled} onChange={e => { const file = e.target.files?.[0]; if (file) void selectReference(file, "sceneReference"); }} /></label>
        <label className="ie-check"><input type="checkbox" disabled={disabled || !value.consistency.sceneReference} checked={!!value.consistency.exactScene} onChange={e => onChange({ ...value, consistency: { ...value.consistency, exactScene: e.target.checked } })} />遵循指定场景</label>
        <label>模特与场景要求<input disabled={disabled} value={value.consistency.instructions || ""} onChange={e => onChange({ ...value, consistency: { ...value.consistency, instructions: e.target.value } })} /></label>
      </>}
    </>}{error && <p role="alert">{error}</p>}
  </div>;
}
import { useState } from "react";
