# 固定版本的通用前景抠图工具

本目录仅新增本地前景推理实验与模型资产，不修改生产工作台、原 HQ-SAM 环境或模型服务，不提交生图任务。它替换的是 `source_layer` 中的人体语义标签与横向背景色猜测；不是替换 Codex Tools 生图。

## 选择

采用官方 **ZhengPeng7/BiRefNet-matting**，通用免 trimap matting，MIT。手机、帽子、包与衣服均属于整个人像前景，不能再由 SCHP 的 `human==0` 强制清掉。

- 官方模型：[BiRefNet-matting](https://huggingface.co/ZhengPeng7/BiRefNet-matting)
- 官方代码及推理说明：[BiRefNet](https://github.com/ZhengPeng7/BiRefNet)
- 固定 revision：`eccde0a8cbdce7ac5fecfeb06340fe7b949e85d9`
- 权重：`model.safetensors`，884,878,856 bytes
- 权重 SHA256：`a9875de5b1e6c8eb5fdaa8c727a82927ce442cdc87ba3abee6a77e6fa46c25bb`
- 完整本地源文件清单与 SHA：`model-manifest.json`。

原有本地 HQ-SAM ViT-B (379,335,069 bytes) 与 Tiny (42,526,881 bytes) 可以继续作为交互分割工具；其本机实验使用预先指定前/背景点，输出默认按阈值分割。它本身不是独立的整前景 alpha matting 替代，不能把人工标点实验当通用自动通过。

## 本机情况与环境隔离

实测 NVIDIA RTX 4060，8188 MiB，驱动 595.79。生产 Python 环境无 torch，ONNX Runtime 1.31.0 仅 CPU/Azure provider。HQ-SAM 实验环境为 torch 2.6.0+cpu、torchvision 0.21.0+cpu，未安装 CUDA torch。

`prepare_assets.py` 下载官方固定 revision，校验预期 SHA，创建本目录 `.venv-cpu`。它通过 `.pth` 只读复用既有 HQ-SAM CPU site-packages，并把必要的新依赖装在自己的 overlay 中；原环境不变。新增版本锁定在 `requirements-cpu-overlay.txt`，实际版本见 `environment-cpu-freeze.txt`。原始官方 requirements 一并保留；其 `numpy<2` 与现有 numpy2 不同，因此 overlay 使用 numpy1.26.4。

CPU overlay 依赖原实验环境路径；正式部署更适合在独立 `venv` 中安装匹配版本 CUDA torch/torchvision、timm、numpy、safetensors、transformers、einops、kornia。不要直接升级生产环境。

官方对标准 1024 推理报告约 3.5GB FP16 显存；该数据不是本机 matting 模型实测。本机 8GB 可作为 1024、batch1、FP16 的合理起点；必须记录实际峰值和时延，不能把 RTX4090 帧率照搬。worker 的 CUDA 请求会在不可用时失败，绝不静默回退 CPU。

## 命令合同

在本目录运行（PowerShell），路径均可换为绝对路径：

```powershell
& ./.venv-cpu/Scripts/python.exe -B -X utf8 ./foreground_worker.py --input "C:/path/source.webp" --output-dir "C:/path/result" --device cpu --size 1024 --threads 4
```

CUDA runtime 使用完全相同脚本与参数，将解释器替换为独立 CUDA venv 的 python，并传 `--device cuda`。

worker 只从本地已校验的源代码和 safetensors 载入；禁用 Hub 联网，不用 `trust_remote_code`，不解析动态 main。模型以 `bb_pretrained=False` 初始化，严格匹配权重，避免暗中下载 backbone。输入先处理 EXIF 方向，再归一化。默认按官方 1024×1024 预处理，浮点 alpha 双线性恢复原图尺寸；不加二值阈值，不做 SCHP 强删、整图色度校正或横向背景色去污染。

输出：

- `alpha.npy`：原尺寸 float32 覆盖率，保留模型浮点信息；正式适配可转为 float64 计算，但不会新增模型精度。
- `alpha16.png`：原尺寸 16位可交换 alpha；`alpha-preview.png` 只用于肉眼观察。
- `source-rgba.png`：原图 RGB 逐像素保持，alpha 为新预测（已有源 alpha 时相乘）。
- `preview-white.png`、`preview-dark.png`：诊断背景合成，仅用于检查边缘，不作为正式生图交付。
- `receipt.json`：源文件/像素哈希、权重/代码版本、实际依赖、时延、显存和输出哈希；`semanticQualityPassed=null`。

## 接入与验收要求

`source_layer` 应读原图 RGB + 此 alpha；不再按衣料或人体标签删除手机/帽子/包。保留 RGB 核心，避免用猜测背景对不透明商品重写像素。遇残留色边，后续只能针对低覆盖率边缘使用估计前景去污染并保留原始 alpha/RGB 对照，不能全图强拉色。

模型输出不是视觉通过证明。验收必须覆盖：完整手机与手、帽沿/发丝、裤腿/鞋、腋下和衣服洞口、背景残留。换色选区与整人像 alpha 是不同语义合同，禁止直接用整前景 alpha 给整个人换色。自动质检至少应单独检查主体/携带物保留、背景残留与边缘不确定区域；同一模型的自信程度和原像素不变不能证明主体完整。

仍有风险：与背景近色的细包带/流苏、被遮挡的手机边缘、复杂建筑缝隙、透明衣料/反光透明商品、超过1024预处理后消失的细发丝。没有证据能保证所有商品0返修；失败必须阻断自动交付并保留证据，不能把人工补点当自动成功。

## 已完成的真实推理

`pink-cpu-v2/receipt.json` 为最终 worker 的一次真实推理；输入为已有任务的 `01-Pink.webp`，sourceFileSHA 与任务上传回执一致。没有模型生成提交、人工打点或手工蒙版。

- 模型输入1024×1024，输出原尺寸750×1000；4线程 CPU float32。
- 模型载入1.169秒，推理17.291秒，总计18.729秒（不包含启动前权重哈希校验）。
- 最终 worker SHA256：`69e7aa69b783bf42cebe69cb8d1abae7b8dcd03f20fd5a7b3eb1d7abb709b7ea`。
- 原图RGB在RGBA文件中保持，另一个Python/Pillow解码环境也独立比对一致；alpha形状、有限值与范围检查通过。两次真实推理的 alpha.npy SHA完全一致。
- `pip check`：无依赖冲突；HQ-SAM原环境仍为torch2.6.0+cpu、huggingface-hub2.4.0，未被卸载/升级。
- 已确认重复使用非空输出目录会立即拒绝，不覆盖已有结果。
- 白底/深底诊断可见手机、手、帽子、裤装保留，旧失败中的大片建筑黑条不再出现。该观察不代表所有发丝/细带通过自动语义验收，回执仍为 `semanticQualityPassed=null`。

`validation.json` 保存独立文件/像素合同核对；`pink-cpu-v1` 保留首次对照，不覆盖它。

依赖安装曾遇到默认pip缓存目录超出workspace可写范围，导致Windows临时文件PermissionError重试空转。已将安装固定为 `--no-cache-dir`，并将运行时HF缓存固定在每次输出目录内，最终推理无全局缓存警告。未修改全局缓存权限。
