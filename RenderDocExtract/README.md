# RenderDoc EID Draw Resource Extractor 使用文档

> 当前文档路径：`D:/UGit/renderdoc/RenderDocExtract/README.md`。

## 1. 项目目标

本工具链用于从 RenderDoc `.rdc` 捕获中按指定 EID 提取一个 DrawCall 的核心渲染资源，并生成可验证、可追踪、可用于 UE 材质/资源重建的输出。

当前已支持：

- 打开固定 RDC 并定位 EID。
- 提取 VS/PS shader：DXIL、disasm、HLSL、signature、RT 信息。
- 提取 PS/VS texture bindings 并导出 DDS。
- 提取 VS/PS cbuffer、StructuredBuffer、RWBuffer 等 buffer 数据。
- 提取 mesh：OBJ 预览、`mesh.json`、`attributes.json/bin` sidecar。
- 生成 EID 级 `draw_manifest.json`。
- 验证 manifest 与 RenderDoc live PipeState 的一致性。
- 匹配 GBuffer layout，并查询 RT/channel/unpack 规则。
- 生成材质属性级 HLSL 切片：`MF_BaseColor()`、`MF_Normal()` 等。
- 将公共 Texture Sample 提取到 `MaterialTextureSamples` + `SampleMaterialTextures()`，避免重复采样。
- 从 PostVS 正确提取 `PRIMITIVE_ID`，用于 StructuredBuffer Load 静态求值。
- 通过 HLSL 资源名解析实际 DDS/bin 文件。
- 通过 `Scripts/gui_app.py` 配置 RDC、qrenderdoc/renderdoc、输出路径和常用参数，并持久化到 `Config/app_settings.json`。

---

## 2. 固定路径与环境

| 项 | 路径 / 值 |
|---|---|
| 项目根目录 | `D:/UGit/renderdoc/RenderDocExtract/` |
| 脚本目录 | `D:/UGit/renderdoc/RenderDocExtract/Scripts/` |
| 输出目录 | `D:/UGit/renderdoc/RenderDocExtract/Output/` |
| 测试目录 | `D:/UGit/renderdoc/RenderDocExtract/Tests/` |
| 日志目录 | `D:/UGit/renderdoc/RenderDocExtract/Logs/` |
| 配置目录 | `D:/UGit/renderdoc/RenderDocExtract/Config/` |
| GUI 持久化配置 | `D:/UGit/renderdoc/RenderDocExtract/Config/app_settings.json` |
| 默认测试 RDC | `D:/PTGameDoc/TLUS2/Pix/TLUS2-PIX/WuKong_Forest0/build/RDC/WuKong_Forest1.rdc` |
| qrenderdoc | `D:/UGit/renderdoc/x64/Release/qrenderdoc.exe` |
| Python | `C:/Users/Boson/AppData/Local/Programs/Python/Python314/python.exe` |
| HLSLDecompiler | `D:/PTGameDoc/TLUS2/Pix/TLUS2-PIX/tools/hlsl_decompiler/HLSLDecompiler.exe` |
| 固定 smoke EID | `7643`、`7955` |

注意：

- 涉及 RenderDoc replay API 的脚本必须通过 `qrenderdoc.exe --python` 运行。
- `extract_eid.py` 是总控脚本，可以用系统 Python 运行，它内部会调用 `qrenderdoc.exe --python`。
- EID `7955` 是 instanced Draw：当前阶段只提取 `extracted_instance=0`，但 manifest 必须保留原始 `numInstances=18`。
- 所有脚本默认写日志到 `Logs/脚本名_YYYYMMDD_HHMMSS.log`，支持 `--no-log` 或 `-Nolog` 关闭日志。

---

## 3. GUI 使用方式

新增 GUI：

```bash
py "D:/UGit/renderdoc/RenderDocExtract/Scripts/gui_app.py"
```

GUI 会自动读取并保存：

```text
D:/UGit/renderdoc/RenderDocExtract/Config/app_settings.json
```

可配置字段包括：

- RDC 文件路径。
- EID。
- Output 目录。
- `qrenderdoc.exe` 路径。
- `renderdoc.exe` 路径，当前主要持久化备用。
- `HLSLDecompiler.exe` 路径。
- GBuffer layout JSON 路径。
- step timeout。
- 是否禁用 log。
- Mesh unit / max indices / JSON vertex limit。
- Texture only-used/all-bound 与外部 texture library。
- RenderDoc Python module dirs。

GUI 按钮：

- `保存配置`：写入 `Config/app_settings.json`。
- `重新加载`：从磁盘恢复。
- `运行完整提取`：调用 `extract_eid.py`。
- `停止运行`：终止当前运行中的提取进程。
- `打开输出目录` / `打开日志目录`。

配置优先级：

```text
显式 CLI 参数 > 环境变量 > Config/app_settings.json > 内置 fallback 默认值
```

---

## 4. 快速开始：完整提取一个 EID

### 3.1 提取 EID 7643

```bash
"C:/Users/Boson/AppData/Local/Programs/Python/Python314/python.exe" \
  "D:/UGit/renderdoc/RenderDocExtract/Scripts/extract_eid.py" \
  --eid 7643 \
  --step-timeout 360
```

或使用 Windows Python launcher：

```bash
py "D:/UGit/renderdoc/RenderDocExtract/Scripts/extract_eid.py" --eid 7643 --step-timeout 360
```

### 3.2 提取 EID 7955

```bash
"C:/Users/Boson/AppData/Local/Programs/Python/Python314/python.exe" \
  "D:/UGit/renderdoc/RenderDocExtract/Scripts/extract_eid.py" \
  --eid 7955 \
  --step-timeout 360
```

或：

```bash
py "D:/UGit/renderdoc/RenderDocExtract/Scripts/extract_eid.py" --eid 7955 --step-timeout 360
```

### 3.3 Output 被清空后的推荐重建命令

```bash
py "D:/UGit/renderdoc/RenderDocExtract/Scripts/extract_eid.py" --eid 7643 --step-timeout 360
py "D:/UGit/renderdoc/RenderDocExtract/Scripts/extract_eid.py" --eid 7955 --step-timeout 360
```

当前 `extract_eid.py` 会执行完整链路：

```text
extract_shaders -> extract_textures -> extract_buffers -> extract_mesh -> build_draw_manifest -> validate_extraction -> extract_primitive_context -> material_hlsl_slice -> validate_material_slices
```

因此完整运行后应生成：

```text
Output/draws/eid_<EID>/draw_manifest.json
Output/draws/eid_<EID>/primitive_context.json
Output/draws/eid_<EID>/material_slices.hlsl
Output/draws/eid_<EID>/material_slices.json
```

---

## 4. 完整输出结构

完整提取后，关键输出如下：

```text
Output/
  draws/
    eid_7643/
      draw_manifest.json
      primitive_context.json
      material_slices.hlsl
      material_slices.json
    eid_7955/
      draw_manifest.json
      primitive_context.json
      material_slices.hlsl
      material_slices.json
  libraries/
    shaders/
      VS/*.dxil
      VS/*.disasm.txt
      VS/*.hlsl
      PS/*.dxil
      PS/*.disasm.txt
      PS/*.hlsl
      shader_library.json
    textures/
      *.dds
      texture_library.json
    buffers/
      *.bin
      decoded_cbuffer_*.json
      buffer_library.json
    meshes/
      *.obj
      *.mesh.json
      *.attributes.json
      *.attributes.bin
      mesh_library.json
```

---

## 5. 单步脚本命令

### 5.1 rd_session.py：打开 RDC、列 Draw、定位 EID

```bash
timeout 360s "D:/UGit/renderdoc/x64/Release/qrenderdoc.exe" \
  --python "D:/UGit/renderdoc/RenderDocExtract/Scripts/rd_session.py"
```

输出示例：

```text
D:/UGit/renderdoc/RenderDocExtract/Tests/rd_session_draws.json
```

### 5.2 extract_shaders.py：提取 shader / HLSL / RT / GBuffer layout

Git Bash：

```bash
RENDERDOC_EXTRACT_EID=7643 timeout 360s "D:/UGit/renderdoc/x64/Release/qrenderdoc.exe" \
  --python "D:/UGit/renderdoc/RenderDocExtract/Scripts/extract_shaders.py"
```

PowerShell：

```powershell
$env:RENDERDOC_EXTRACT_EID="7643"
& "D:/UGit/renderdoc/x64/Release/qrenderdoc.exe" --python "D:/UGit/renderdoc/RenderDocExtract/Scripts/extract_shaders.py"
Remove-Item Env:\RENDERDOC_EXTRACT_EID
```

关键输出：

```text
Output/libraries/shaders/shader_library.json
Tests/extract_shaders_eid_7643.json
```

### 5.3 extract_textures.py：提取 texture bindings 并导出 DDS

```bash
RENDERDOC_EXTRACT_EID=7643 timeout 360s "D:/UGit/renderdoc/x64/Release/qrenderdoc.exe" \
  --python "D:/UGit/renderdoc/RenderDocExtract/Scripts/extract_textures.py"
```

关键输出：

```text
Output/libraries/textures/*.dds
Output/libraries/textures/texture_library.json
Tests/extract_textures_eid_7643.json
```

### 5.4 extract_buffers.py：提取 cbuffer / StructuredBuffer / RWBuffer

```bash
RENDERDOC_EXTRACT_EID=7643 timeout 360s "D:/UGit/renderdoc/x64/Release/qrenderdoc.exe" \
  --python "D:/UGit/renderdoc/RenderDocExtract/Scripts/extract_buffers.py"
```

关键输出：

```text
Output/libraries/buffers/*.bin
Output/libraries/buffers/decoded_cbuffer_*.json
Output/libraries/buffers/buffer_library.json
Tests/extract_buffers_eid_7643.json
```

### 5.5 extract_mesh.py：提取 Mesh/OBJ/attributes sidecar

```bash
RENDERDOC_EXTRACT_EID=7643 timeout 360s "D:/UGit/renderdoc/x64/Release/qrenderdoc.exe" \
  --python "D:/UGit/renderdoc/RenderDocExtract/Scripts/extract_mesh.py"
```

Instanced Draw 示例：

```bash
RENDERDOC_EXTRACT_EID=7955 timeout 360s "D:/UGit/renderdoc/x64/Release/qrenderdoc.exe" \
  --python "D:/UGit/renderdoc/RenderDocExtract/Scripts/extract_mesh.py"
```

关键输出：

```text
Output/libraries/meshes/*.obj
Output/libraries/meshes/*.mesh.json
Output/libraries/meshes/*.attributes.json
Output/libraries/meshes/*.attributes.bin
Output/libraries/meshes/mesh_library.json
Tests/extract_mesh_eid_7643.json
Tests/extract_mesh_eid_7955.json
```

### 5.6 build_draw_manifest.py：生成最终 draw manifest

```bash
RENDERDOC_EXTRACT_EID=7643 timeout 360s "D:/UGit/renderdoc/x64/Release/qrenderdoc.exe" \
  --python "D:/UGit/renderdoc/RenderDocExtract/Scripts/build_draw_manifest.py"
```

关键输出：

```text
Output/draws/eid_7643/draw_manifest.json
Tests/build_manifest_eid_7643.json
```

### 5.7 extract_primitive_context.py：提取 PRIMITIVE_ID 上下文

```bash
RENDERDOC_EXTRACT_EID=7643 timeout 180s "D:/UGit/renderdoc/x64/Release/qrenderdoc.exe" \
  --python "D:/UGit/renderdoc/RenderDocExtract/Scripts/extract_primitive_context.py"
```

输出：

```text
Output/draws/eid_7643/primitive_context.json
```

已验证值：

| EID | PRIMITIVE_ID | 说明 |
|---:|---:|---|
| 7643 | 708 | PostVS 前 64 个 sample 一致 |
| 7955 | 3964 | PostVS 前 64 个 sample 一致 |

### 5.8 material_hlsl_slice.py：生成材质属性 HLSL 切片

```bash
py "D:/UGit/renderdoc/RenderDocExtract/Scripts/material_hlsl_slice.py" --eid 7643
py "D:/UGit/renderdoc/RenderDocExtract/Scripts/material_hlsl_slice.py" --eid 7955
```

输出：

```text
Output/draws/eid_7643/material_slices.hlsl
Output/draws/eid_7643/material_slices.json
Output/draws/eid_7955/material_slices.hlsl
Output/draws/eid_7955/material_slices.json
```

---

## 6. 验证命令

### 6.1 语法检查

```bash
"C:/Users/Boson/AppData/Local/Programs/Python/Python314/python.exe" -m py_compile \
  "D:/UGit/renderdoc/RenderDocExtract/Scripts/extract_eid.py" \
  "D:/UGit/renderdoc/RenderDocExtract/Scripts/validate_extraction.py" \
  "D:/UGit/renderdoc/RenderDocExtract/Scripts/material_hlsl_slice.py" \
  "D:/UGit/renderdoc/RenderDocExtract/Scripts/validate_material_slices.py" \
  "D:/UGit/renderdoc/RenderDocExtract/Scripts/resolve_hlsl_resource.py"
```

### 6.2 验证 manifest 与 RenderDoc live PipeState 是否一致

EID 7643：

```bash
RENDERDOC_EXTRACT_EID=7643 timeout 360s "D:/UGit/renderdoc/x64/Release/qrenderdoc.exe" \
  --python "D:/UGit/renderdoc/RenderDocExtract/Scripts/validate_extraction.py"
```

EID 7955：

```bash
RENDERDOC_EXTRACT_EID=7955 timeout 360s "D:/UGit/renderdoc/x64/Release/qrenderdoc.exe" \
  --python "D:/UGit/renderdoc/RenderDocExtract/Scripts/validate_extraction.py"
```

输出：

```text
Tests/validate_extraction_eid_7643.json
Tests/validate_extraction_eid_7955.json
```

期望：

```json
{
  "status": "passed",
  "errors": [],
  "warnings": []
}
```

验证内容包括：

- `draw_manifest.json` 是否存在。
- shader/texture/buffer/mesh 引用文件是否存在。
- DDS hash 是否一致。
- buffer `.bin` hash 是否一致。
- VS/PS texture bindings 是否与 RenderDoc live `PipeState.GetReadOnlyResources()` 一致。
- VS/PS buffer bindings 是否与 RenderDoc live constant/read-only/read-write resources 一致。
- instanced Draw 是否记录 `extracted_instance=0`。

### 6.3 验证材质 HLSL 切片

```bash
py "D:/UGit/renderdoc/RenderDocExtract/Scripts/validate_material_slices.py" --eid 7643
py "D:/UGit/renderdoc/RenderDocExtract/Scripts/validate_material_slices.py" --eid 7955
```

输出：

```text
Tests/validate_material_slices_eid_7643.json
Tests/validate_material_slices_eid_7955.json
```

验证内容包括：

- `MF_BaseColor(samples)` 等函数是否存在。
- `frag_main_BaseColor()` 等 wrapper 是否存在。
- HLSL 顶部是否包含 cbuffer / Buffer / Texture / Sampler 声明。
- cbuffer placeholder 是否包含 source、file、value。
- StructuredBuffer placeholder 是否包含 source、register、file、element size、symbolic index、static index、value。
- 公共采样函数 `SampleMaterialTextures()` 和 `MaterialTextureSamples` 是否存在。

---

## 7. 已知 good sample 结果

### 7.1 EID 7643

| 项 | 结果 |
|---|---|
| numIndices | 91704 |
| numInstances | 1 |
| VS | `vs_e6c6c5db88288f64` |
| PS | `ps_3acb40051dd13bd4` |
| Mesh | `mesh_e104e718b4faa2e7` |
| Mesh status | `ok` |
| RT count | 6 |
| Depth | `D32S8` |
| Blend | `opaque` |
| GBuffer layout | `ue5_legacy_velocity_no_precshadow` |
| PRIMITIVE_ID | 708 |

Texture 绑定统计：

| Stage | Texture Bindings | Unique Textures |
|---|---:|---:|
| VS | 0 | 0 |
| PS | 4 | 4 |

Buffer 绑定统计：

| Stage | Total | ConstantBuffer | ReadOnly Buffer | ReadWrite Buffer |
|---|---:|---:|---:|---:|
| VS | 11 | 4 | 7 | 0 |
| PS | 5 | 3 | 1 | 1 |

### 7.2 EID 7955

| 项 | 结果 |
|---|---|
| numIndices | 1302 |
| numInstances | 18 |
| extracted_instance | 0 |
| VS | `vs_231fdf81edfafc38` |
| PS | `ps_b147662ba0cf95dc` |
| Mesh | `mesh_ab402735f71d4cad` |
| Mesh status | `ok` |
| RT count | 6 |
| Depth | `D32S8` |
| Blend | `opaque` |
| GBuffer layout | `ue5_legacy_velocity_no_precshadow` |
| PRIMITIVE_ID | 3964 |

Texture 绑定统计：

| Stage | Texture Bindings | Unique Textures |
|---|---:|---:|
| VS | 5 | 4 |
| PS | 5 | 4 |

Buffer 绑定统计：

| Stage | Total | ConstantBuffer | ReadOnly Buffer | ReadWrite Buffer |
|---|---:|---:|---:|---:|
| VS | 14 | 6 | 8 | 0 |
| PS | 5 | 3 | 1 | 1 |

---

## 8. SVT 还原

当前 EID `7643` 的 PS 中存在 Streaming Virtual Texture 采样：

| HLSL 资源 | register | 作用 | 文件 |
|---|---|---|---|
| `_15` | `t2` | page table，`R32G32_UINT` | `Output/libraries/textures/R32G32_UINT_000001.dds` |
| `_16` | `t3` | physical atlas A，BC3 | `Output/libraries/textures/BC3_TYPELESS_000001.dds` |
| `_17` | `t4` | physical atlas B，BC1 | `Output/libraries/textures/BC1_TYPELESS_000002.dds` |

新增脚本：

```text
Scripts/reconstruct_svt.py
Scripts/validate_svt_reconstruction.py
Scripts/dds_utils.py
```

### 8.1 生成 SVT 还原贴图

安全预览尺寸，默认不会直接生成 16K 巨图：

```bash
py "D:/UGit/renderdoc/RenderDocExtract/Scripts/reconstruct_svt.py" \
  --eid 7643 \
  --page-table _15 \
  --physical-a _16 \
  --physical-b _17 \
  --tile-size 128 \
  --border 4 \
  --tile-pitch 136 \
  --max-virtual-size 1024
```

如果要生成 full 16K，请显式打开大图输出：

```bash
py "D:/UGit/renderdoc/RenderDocExtract/Scripts/reconstruct_svt.py" \
  --eid 7643 \
  --max-virtual-size 16384 \
  --allow-large-output
```

注意：16K RGBA8 单张约 1GB，两张约 2GB。

输出：

```text
Output/draws/eid_7643/svt_reconstruction/svt_reconstruction.json
Output/draws/eid_7643/svt_reconstruction/svt_sampling_replacement.hlsl
Output/libraries/textures/reconstructed_svt/eid_7643__16_reconstructed.dds
Output/libraries/textures/reconstructed_svt/eid_7643__17_reconstructed.dds
```

还原出的贴图会注册到：

```text
Output/libraries/textures/texture_library.json
```

### 8.2 验证 SVT 还原输出

```bash
py "D:/UGit/renderdoc/RenderDocExtract/Scripts/validate_svt_reconstruction.py" --eid 7643
```

验证内容：

- 输出 DDS 是否存在。
- DDS header 尺寸是否与 `svt_reconstruction.json` 一致。
- 是否有 page 被复制。
- 是否注册到 `texture_library.json`。
- replacement HLSL 是否包含 `RENDERDOCEXTRACT_USE_RECONSTRUCTED_SVT` 宏。

### 8.3 替换采样代码

生成的：

```text
Output/draws/eid_7643/svt_reconstruction/svt_sampling_replacement.hlsl
```

包含宏：

```hlsl
RENDERDOCEXTRACT_USE_RECONSTRUCTED_SVT
```

宏打开时使用还原出的 virtual texture；宏关闭时保留原 page table 路径注释。

---

## 9. GBuffer layout 匹配与通道查询

配置文件：

```text
Config/gbuffer_layouts.json
```

当前两个 smoke EID 均匹配：

```text
ue5_legacy_velocity_no_precshadow
```

RT 对应关系：

| RT | Name | Format | 语义 |
|---:|---|---|---|
| RT0 | Lighting | `R16G16B16A16_FLOAT` | SceneColor / Lighting |
| RT1 | GBufferA | `R10G10B10A2_UNORM` | WorldNormal + PerObjectData |
| RT2 | GBufferB | `B8G8R8A8_UNORM` | Metallic / Specular / Roughness / ShadingModelID |
| RT3 | GBufferC | `B8G8R8A8_SRGB` | BaseColor RGB + AO/IndirectIrradiance A |
| RT4 | Velocity | `R16G16B16A16_UNORM` | Velocity XY + DeviceZ delta / flags BA |
| RT5 | GBufferD | `B8G8R8A8_UNORM` | CustomData / Subsurface / Opacity 等 |

### 8.1 查询 RT4.A 是什么

```bash
py "D:/UGit/renderdoc/RenderDocExtract/Scripts/gbuffer_layout_match.py" query \
  --layout-id ue5_legacy_velocity_no_precshadow \
  --rt 4 \
  --channel A
```

### 8.2 unpack GBufferB.A

```bash
py "D:/UGit/renderdoc/RenderDocExtract/Scripts/gbuffer_layout_match.py" query \
  --layout-id ue5_legacy_velocity_no_precshadow \
  --rt 2 \
  --channel A \
  --value 151
```

会解析：

- `ShadingModelID`
- `ShadingModel`
- `SelectiveOutputMask`
- `HAS_ANISOTROPY_MASK`
- `SKIP_PRECSHADOW_MASK`
- `ZERO_PRECSHADOW_or_IS_FIRST_PERSON`
- `SKIP_VELOCITY_MASK`

### 8.3 单独运行 layout match

```bash
py "D:/UGit/renderdoc/RenderDocExtract/Scripts/gbuffer_layout_match.py" match \
  --hlsl "D:/UGit/renderdoc/RenderDocExtract/Output/libraries/shaders/PS/PS_3acb40051dd13bd4.hlsl" \
  --render-targets-json "D:/UGit/renderdoc/RenderDocExtract/Output/draws/eid_7643/draw_manifest.json" \
  --out "D:/UGit/renderdoc/RenderDocExtract/Tests/gbuffer_match_eid_7643.json"
```

---

## 9. 材质属性 HLSL 切片说明

生成脚本：

```text
Scripts/material_hlsl_slice.py
```

输出：

```text
Output/draws/eid_<EID>/material_slices.hlsl
Output/draws/eid_<EID>/material_slices.json
```

### 9.1 当前生成的材质函数

| 函数 | 输出 |
|---|---|
| `MF_BaseColor(MaterialTextureSamples samples)` | `float3` |
| `MF_Normal(MaterialTextureSamples samples)` | `float3` |
| `MF_AO(MaterialTextureSamples samples)` | `float` |
| `MF_Roughness(MaterialTextureSamples samples)` | `float` |
| `MF_Specular(MaterialTextureSamples samples)` | `float` |
| `MF_Metallic(MaterialTextureSamples samples)` | `float` |
| `MF_SubsurfaceColor(MaterialTextureSamples samples)` | `float3` |
| `MF_Opacity(MaterialTextureSamples samples)` | `float` |
| `MF_OpacityMask()` | 当前无专用 GBuffer 通道，保留空函数 / 默认值 |

### 9.2 公共贴图采样结构

示例结构：

```hlsl
struct MaterialTextureSamples
{
    float Sample_1; // _12.SampleBias(...) used by BaseColor, AO, Roughness, Specular, SubsurfaceColor
};

MaterialTextureSamples SampleMaterialTextures()
{
    MaterialTextureSamples samples;
    // source line ...
    // UV / bias 等前置计算
    samples.Sample_1 = _12.SampleBias(...).x;
    return samples;
}
```

材质函数使用：

```hlsl
float3 MF_BaseColor(MaterialTextureSamples samples)
{
    // samples.Sample_1 可被多个材质属性复用
    return float3(SV_Target_3.x, SV_Target_3.y, SV_Target_3.z);
}
```

### 9.3 cbuffer 常量替换

源 HLSL：

```hlsl
_26_m0[46u].w
```

生成：

```hlsl
// BaseColor_Scalar_1: source _26_m0[46u].w; cbuffer register(b0); file cbuffer_xxx.bin; byte_offset 736; value 0.100000001
static const float BaseColor_Scalar_1 = 0.100000001;
```

### 9.4 StructuredBuffer Load 替换

源 HLSL：

```hlsl
_8.Load(_691).x
```

若 `_691` 可追踪为：

```hlsl
(PRIMITIVE_ID * 160u) + 128u
```

且 `primitive_context.json` 中 `PRIMITIVE_ID=708`，则生成：

```hlsl
// BaseColor_Scalar_sb_1: source _8.Load(_691).x;
// _8 register(t0); file buffer_xxx.bin; element_size 4;
// symbolic_index (((PRIMITIVE_ID * 160u) + 128u)); primitive_id 708;
// static_index 113408; static_value 0
static const uint BaseColor_Scalar_sb_1 = 0;
```

---

## 10. 通过 HLSL 资源名解析实际文件

脚本：

```text
Scripts/resolve_hlsl_resource.py
```

### 10.1 查询 `_8`

```bash
py "D:/UGit/renderdoc/RenderDocExtract/Scripts/resolve_hlsl_resource.py" --eid 7643 --name _8
```

典型输出：

```json
{
  "hlsl_name": "_8",
  "kind": "read_only_buffer",
  "shader_resource_name": "StructuredBuffer0",
  "resource_id": "4534",
  "library_file": "buffer_37ce53f878450c54.bin",
  "absolute_path": "D:/UGit/renderdoc/RenderDocExtract/Output/libraries/buffers/buffer_37ce53f878450c54.bin"
}
```

### 10.2 查询 `_12`

```bash
py "D:/UGit/renderdoc/RenderDocExtract/Scripts/resolve_hlsl_resource.py" --eid 7643 --name _12
```

典型输出：

```json
{
  "hlsl_name": "_12",
  "kind": "texture",
  "shader_resource_name": "Texture2D1",
  "resource_id": "1779",
  "format": "BC1_TYPELESS",
  "library_file": "BC1_TYPELESS_000001.dds",
  "absolute_path": "D:/UGit/renderdoc/RenderDocExtract/Output/libraries/textures/BC1_TYPELESS_000001.dds"
}
```

---

## 11. 常见问题与防踩坑

### 11.1 qrenderdoc 卡住

不要直接无超时前台运行大型 replay 脚本。推荐：

```bash
timeout 360s "D:/UGit/renderdoc/x64/Release/qrenderdoc.exe" --python ".../script.py"
```

如果卡住，检查并结束 `qrenderdoc.exe` 进程。

### 11.2 系统 Python 不能直接跑 RenderDoc replay 脚本

仓库内的 `renderdoc.py` wrapper 不是完整 standalone replay 模块。涉及 `OpenCaptureFile` / `ReplayController` 的脚本必须通过：

```bash
qrenderdoc.exe --python script.py
```

### 11.3 OBJ 全是 `v 0 0 0`

优先检查：

```text
Output/libraries/meshes/*.attributes.json
```

EID `7643/7955` 的 position-like attribute 是：

```text
ATTRIBUTE0 R32G32B32_FLOAT
```

即使没有传统 `POSITION` semantic，也不能直接判断没有 position。

### 11.4 同格式 DDS hash mismatch

texture library key 必须使用：

```text
sha256(format | dds_sha256)
```

不能把 `format + sha256` 的长公共前缀直接传给会截断的 key 生成函数。

### 11.5 `static uint _1176;` 是什么

这类变量通常是 HLSL 反编译器生成的 static placeholder，用于填充：

```hlsl
asfloat(uint2(_1176, value)).y
```

它不是 cbuffer、不是 StructuredBuffer、不是 Texture。若切片中引用，应保留 static declaration。

---

## 12. 推荐开发/验证流程

### 12.1 清空 Output 后全量重建

```bash
py "D:/UGit/renderdoc/RenderDocExtract/Scripts/extract_eid.py" --eid 7643 --step-timeout 360
py "D:/UGit/renderdoc/RenderDocExtract/Scripts/extract_eid.py" --eid 7955 --step-timeout 360
```

### 12.2 补 primitive context 与 material slices

```bash
RENDERDOC_EXTRACT_EID=7643 timeout 180s "D:/UGit/renderdoc/x64/Release/qrenderdoc.exe" --python "D:/UGit/renderdoc/RenderDocExtract/Scripts/extract_primitive_context.py"
RENDERDOC_EXTRACT_EID=7955 timeout 180s "D:/UGit/renderdoc/x64/Release/qrenderdoc.exe" --python "D:/UGit/renderdoc/RenderDocExtract/Scripts/extract_primitive_context.py"

py "D:/UGit/renderdoc/RenderDocExtract/Scripts/material_hlsl_slice.py" --eid 7643
py "D:/UGit/renderdoc/RenderDocExtract/Scripts/material_hlsl_slice.py" --eid 7955
```

### 12.3 最终验证

```bash
RENDERDOC_EXTRACT_EID=7643 timeout 360s "D:/UGit/renderdoc/x64/Release/qrenderdoc.exe" --python "D:/UGit/renderdoc/RenderDocExtract/Scripts/validate_extraction.py"
RENDERDOC_EXTRACT_EID=7955 timeout 360s "D:/UGit/renderdoc/x64/Release/qrenderdoc.exe" --python "D:/UGit/renderdoc/RenderDocExtract/Scripts/validate_extraction.py"

py "D:/UGit/renderdoc/RenderDocExtract/Scripts/validate_material_slices.py" --eid 7643
py "D:/UGit/renderdoc/RenderDocExtract/Scripts/validate_material_slices.py" --eid 7955
```

期望全部为：

```json
"status": "passed",
"errors": [],
"warnings": []
```

---

## 13. 当前可继续扩展方向

1. 更多 pixel/primitive/sample context：支持不同像素命中的不同 `PRIMITIVE_ID`。
2. UE Material Function 导入格式化：将 `MF_*` 输出进一步整理为 UE 可自动导入的材质函数描述。
3. GLB/glTF 后处理：基于 `mesh.json + attributes.bin/json` 生成交换格式。
4. 批量 EID 提取：对一组 EID 自动运行 extract/validate/material slice。
5. 更细 GBuffer/材质语义推断：结合 ShadingModelID、CustomData、SubsurfaceColor、Opacity 等自动分类材质类型。
