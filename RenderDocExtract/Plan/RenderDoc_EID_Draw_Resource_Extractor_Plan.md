# RenderDoc EID Draw 资源提取器 - 第一阶段实施计划

## 0. 目标边界

目标：给定一个 `.rdc` 和一个 `EID/EventId`，把该 Draw 在 VS/PS 阶段复刻所需的资源提取到可复用资产库，并生成该 EID 的 `draw_manifest.json`。本阶段只做资源提取与元数据建模，不做 UE 导入。

优先策略：**先用 RenderDoc Python Replay API 实现通用脚本工具链，不立即改 RenderDoc C++ 源码**。原因是现有 API 已覆盖 SetFrameEvent、PipelineState、ShaderReflection、DescriptorAccess、SaveTexture、GetBufferData、GetCBufferVariableContents、GetPostVSData 等核心能力。源码扩展只作为验证后发现 Python API 无法精确获取时的候选方案。

## 1. 固定工程目录与文档规则

所有本功能相关输出、脚本、计划、测试产物统一放在：

```text
D:/UGit/renderdoc/RenderDocExtract/
```

目录约定：

```text
D:/UGit/renderdoc/RenderDocExtract/
  Plan/
    RenderDoc_EID_Draw_Resource_Extractor_Plan.md    # 当前计划落盘位置
    踩坑.md                                          # 持续维护，记录错误/误判/修复方式
  Scripts/
    rd_session.py
    library_db.py
    extract_eid.py
    extract_textures.py
    extract_shaders.py
    extract_mesh.py
    extract_buffers.py
    build_draw_manifest.py
    validate_extraction.py
  Output/
    libraries/
      textures/
      shaders/
      meshes/
      buffers/
    draws/
  Temp/
  Tests/
  Logs/
    脚本名_YYYYMMDD_HHMMSS.log
```

执行开发时的第一步：
1. 创建 `D:/UGit/renderdoc/RenderDocExtract/` 目录结构。
2. 将当前计划复制/落盘为 `D:/UGit/renderdoc/RenderDocExtract/Plan/RenderDoc_EID_Draw_Resource_Extractor_Plan.md`。
3. 创建并持续维护 `D:/UGit/renderdoc/RenderDocExtract/Plan/踩坑.md`。
4. 后续所有开发计划、阶段复盘、测试结论都必须以 `RenderDocExtract/Plan/` 下的内容为准。

## 2. 测试门禁

测试 RDC 固定为：

```text
D:/PTGameDoc/TLUS2/Pix/TLUS2-PIX/WuKong_Forest0/build/RDC/WuKong_Forest1.rdc
```

固定测试 EID：
- `7643`：普通 Draw smoke test。
- `7955`：Instanced Draw smoke test。

Instanced Draw 处理规则：
- 如果遇到 instanced 绘制，本阶段只提取第一个 instance 的数据，即 `instance=0` / `instanceOffset` 按 RenderDoc 当前 ActionDescription 与 vertex buffer 规则处理。
- Mesh/Buffer/Shader/Texture manifest 中必须记录原始 `numInstances` 和实际提取的 `extracted_instance=0`，避免误以为完整导出了所有 instance。
- 后续如需完整还原所有 instance，再扩展 instance 循环导出；当前第一阶段不做。

硬性规则：
- **每完成一个 Python 脚本，都必须单独测试通过后才能开发下一个脚本。**
- 每个脚本至少要支持 `--help`、参数校验、错误日志。
- 每个脚本默认输出关键调试信息到 `D:/UGit/renderdoc/RenderDocExtract/Logs/`，日志文件命名为 `脚本名_YYYYMMDD_HHMMSS.log`，例如 `extract_shaders_20260606_203945.log`。
- 每个脚本必须支持关闭日志参数：同时接受 `--no-log` 和 `-Nolog`，用户显式指定后不生成 log 文件。
- 每个脚本的 log 至少记录：命令行参数、RDC 路径、EID、输出目录、关键 RenderDoc API 调用阶段、提取到的资源数量、warning/error、耗时。
- 每个脚本测试结果写入：`D:/UGit/renderdoc/RenderDocExtract/Tests/`。
- 对用户需要人工确认产物的关键步骤，完成脚本开发和自测后必须停下来，等待用户确认输出没问题后才能继续下一步。
- 必须持续维护 `D:/UGit/renderdoc/RenderDocExtract/Plan/开发状态.md`，记录当前步骤、脚本状态、测试状态、是否等待用户确认、下一步。
- 每次遇到脚本错误、RenderDoc API 误用、路径问题、格式判断错误、descriptor 误判，都追加到 `Plan/踩坑.md`，格式如下：

```md
## YYYY-MM-DD - 问题标题
- 现象：
- 根因：
- 修复：
- 防复发规则：
```

推荐测试 EID：固定优先使用 `7643` 和 `7955`。其中 `7955` 是 instanced Draw，用于验证“只取第一个 instance”的处理路径；如果用户之后指定 EID，则在不替代这两个 smoke test 的前提下额外测试用户指定 EID。

人工确认门禁：
- `extract_shaders.py`：自测通过后必须停下；用户需要在 shader 文件夹中确认 HLSL/raw/disasm 输出正确后，才能继续 `extract_textures.py`。
- `extract_textures.py`：自测通过后必须停下；用户确认 DDS 与 texture library 输出正确后，才能继续 `extract_buffers.py`。
- `extract_buffers.py`：自测通过后必须停下；用户确认 buffer raw/decoded JSON 输出正确后，才能继续 `extract_mesh.py`。
- `extract_mesh.py`：自测通过后必须停下；用户确认 OBJ 与 attributes sidecar 输出正确后，才能继续 `build_draw_manifest.py`。
- `build_draw_manifest.py`：自测通过后必须停下；用户确认 draw manifest 内容正确后，才能继续集成总控脚本或验证脚本。

## 3. 已确认的源码/API 接入点

| 能力 | 现有接口/结构 | 路径 |
|---|---|---|
| 打开 capture / 定位 EID | `OpenCaptureFile`, `OpenCapture`, `ReplayController.SetFrameEvent` | `renderdoc/api/replay/renderdoc_replay.h` |
| Draw 树与 draw 参数 | `GetRootActions`, `ActionDescription` | `renderdoc/api/replay/data_types.h` |
| 通用 PipelineState | `PipeState` | `renderdoc/api/replay/pipestate.h`, `pipestate.inl` |
| Shader 反射/raw bytes | `ShaderReflection.rawBytes`, `inputSignature`, `outputSignature`, `constantBlocks`, `readOnlyResources` | `renderdoc/api/replay/shader_types.h` |
| Descriptor 绑定与实际资源 | `DescriptorAccess`, `UsedDescriptor`, `Descriptor`, `SamplerDescriptor` | `renderdoc/api/replay/common_pipestate.h` |
| 贴图导出 | `TextureSave`, `SaveTexture`, `GetTextureData`, `TextureDescription` | `renderdoc/api/replay/renderdoc_replay.h`, `data_types.h` |
| Buffer 读回 | `GetBufferData`, `BufferDescription`, descriptor byte range | `renderdoc/api/replay/renderdoc_replay.h`, `data_types.h` |
| ConstantBuffer 变量解析 | `GetCBufferVariableContents`, `ConstantBlock`, `ShaderConstant` | `renderdoc/api/replay/renderdoc_replay.h`, `shader_types.h` |
| Mesh input 解码参考 | `GetIBuffer`, `GetVBuffers`, `GetVertexInputs` | `docs/python_api/examples/renderdoc/decode_mesh.py` |
| Shader/CB 示例 | `fetch_shader.py` | `docs/python_api/examples/renderdoc/fetch_shader.py` |
| DDS 保存示例 | `save_texture.py` | `docs/python_api/examples/renderdoc/save_texture.py` |
| renderdoccmd 扩展候选 | `Command` 注册体系 | `renderdoccmd/renderdoccmd.cpp`, `renderdoccmd/renderdoccmd.h` |

## 4. 最终输出目录结构

默认输出根目录：

```text
D:/UGit/renderdoc/RenderDocExtract/Output/
```

结构：

```text
Output/
  libraries/
    textures/
      texture_library.json
      BC7_UNORM_SRGB_000001.dds
    shaders/
      shader_library.json
      VS_<hash>.dxbc
      VS_<hash>.disasm.txt
      VS_<hash>.hlsl
      PS_<hash>.dxbc
      PS_<hash>.disasm.txt
      PS_<hash>.hlsl
    meshes/
      mesh_library.json
      mesh_<hash>.obj                         # 预览/兼容输出，不作为无损主格式
      mesh_<hash>.glb                         # 推荐交换格式，便于 Python 编辑与现代工具链处理
      mesh_<hash>.attributes.json             # 无损属性布局 sidecar
      mesh_<hash>.attributes.bin              # 无损属性原始数据 sidecar
      mesh_<hash>.mesh.json                   # RenderDoc/UE 重建所需的 mesh manifest
    buffers/
      buffer_library.json
      buffer_<hash>.bin
      cbuffer_<hash>.json
  draws/
    eid_<EID>/
      draw_manifest.json
      extraction_log.json
```

说明：OBJ 无法原生保留所有 vertex attribute，因此只作为预览/兼容输出。Mesh 的推荐策略是：

- **无损主格式**：`mesh_<hash>.mesh.json + mesh_<hash>.attributes.bin`，保存 RenderDoc 原始 vertex/index buffer 切片、layout、semantic、format、stride、offset、instance 信息。这是二次加工和 UE 自定义导入的权威数据。
- **推荐交换格式**：`mesh_<hash>.glb`/glTF 2.0。优点是开放标准、Python 工具丰富（如 `trimesh`、`pygltflib`、Blender Python）、可保存多个 UV/color/tangent，并可通过 `_CUSTOM` attribute 或 `extras` 携带部分自定义属性。缺点是 UE 默认 glTF importer/插件不一定保留全部自定义 vertex attribute，因此不能作为唯一权威数据。
- **预览格式**：`mesh_<hash>.obj`。只保证 position/normal/uv 基本可视化。
- **FBX 定位**：可作为可选 convenience export，但不作为主格式。FBX 对 UE 友好，但格式专有，Python 编辑依赖 Autodesk FBX SDK/Blender，自动化和自定义 vertex attribute 保真都不如 glTF + sidecar 稳定。

结论：第一阶段默认输出 OBJ + 无损 sidecar；实现稳定后增加 GLB；FBX 仅作为可选后处理导出，不作为去重和 UE 重建的权威依据。

## 5. 脚本拆分与逐脚本测试

所有脚本放在：

```text
D:/UGit/renderdoc/RenderDocExtract/Scripts/
```

### 5.1 `rd_session.py` - 第一优先级

职责：RenderDoc Python API 会话封装。

核心函数：
- `open_capture(rdc_path) -> (cap, controller)`
- `find_action_by_eid(controller, eid) -> ActionDescription`
- `set_eid(controller, eid) -> (action, pipe)`
- `resource_maps(controller) -> textures_by_id, buffers_by_id, resources_by_id`
- `list_draws(controller) -> draw summary`

单脚本测试：
```bash
python D:/UGit/renderdoc/RenderDocExtract/Scripts/rd_session.py --rdc D:/PTGameDoc/TLUS2/Pix/TLUS2-PIX/WuKong_Forest0/build/RDC/WuKong_Forest1.rdc --list-draws --limit 50 --out D:/UGit/renderdoc/RenderDocExtract/Tests/rd_session_draws.json
```

通过标准：能打开 RDC，输出前 50 个 draw/action，能找到固定测试 EID `7643` 和 `7955`，并能识别 `7955` 的 `numInstances > 1`。

### 5.2 `library_db.py` - 第二优先级

职责：JSON 资产库读写、hash 去重、原子写入。

核心函数：
- `sha256_file(path)`
- `sha256_bytes(data)`
- `load_json_db(path)`
- `atomic_write_json(path, data)`
- `register_asset(db_path, key, item)`
- `next_index_by_format(db, format_name)`

单脚本测试：
```bash
python D:/UGit/renderdoc/RenderDocExtract/Scripts/library_db.py --self-test --out D:/UGit/renderdoc/RenderDocExtract/Tests/library_db_test/
```

通过标准：重复注册同一 hash 不产生重复项；JSON 可读写；文件名 index 稳定递增。

### 5.3 `extract_shaders.py` - 第三优先级

职责：提取 VS/PS raw shader、disassembly、HLSL、signature 元数据。

核心流程：
1. `pipe.GetShaderReflection(Vertex/Pixel)` 获取 `ShaderReflection`。
2. 保存 `rawBytes` 为 `.dxbc/.dxil/.spv/.bin`，扩展名由 `ShaderReflection.encoding` 决定。
3. hash key = `stage + entryPoint + encoding + sha256(rawBytes)`。
4. `controller.DisassembleShader(pipe.GetGraphicsPipelineObject(), refl, target)` 保存 `.disasm.txt`。
5. 调用 `D:/PTGameDoc/TLUS2/Pix/TLUS2-PIX/tools/hlsl_decompiler` 生成 `.hlsl`；失败写 warning，不阻塞。
6. VS 记录 `inputSignature/outputSignature`；PS 记录 `inputSignature` 与 RT 数量/格式。

单脚本测试：
```bash
python D:/UGit/renderdoc/RenderDocExtract/Scripts/extract_shaders.py --rdc D:/PTGameDoc/TLUS2/Pix/TLUS2-PIX/WuKong_Forest0/build/RDC/WuKong_Forest1.rdc --eid <测试EID> --out D:/UGit/renderdoc/RenderDocExtract/Output --test-log D:/UGit/renderdoc/RenderDocExtract/Tests/extract_shaders_eid_<EID>.json
```

通过标准：VS/PS 至少能保存 raw 与 disasm；HLSL 成功或明确记录失败原因；`shader_library.json` 去重有效。

### 5.4 `extract_textures.py` - 第四优先级

职责：提取 VS/PS 用到的贴图。

核心流程：
1. `pipe.GetReadOnlyResources(stage, onlyUsed=True)`，stage 限定 `Vertex` 和 `Pixel`。
2. 过滤 `UsedDescriptor.descriptor.resource` 为 texture 的资源。
3. 读取 `TextureDescription`：format、width、height、mips、arraysize、msSamp、type。
4. 用临时 DDS 路径调用：`TextureSave.resourceId`, `destType=FileType.DDS`, `mip=-1`, `slice=-1`, `alpha=Preserve`。
5. 对导出的 DDS bytes 做内容 hash；hash key = `format + dimensions + mips + arraysize + dds_sha256`。
6. 若库中已存在，不重复导出；否则按 `格式_Idx.dds` 移入贴图库。
7. 记录 descriptor slot：stage、descriptor type、reflection index、arrayElement、fixedBindNumber、space/set、descriptorStore、byteOffset、view format、firstMip/slice、sampler。

单脚本测试：
```bash
python D:/UGit/renderdoc/RenderDocExtract/Scripts/extract_textures.py --rdc D:/PTGameDoc/TLUS2/Pix/TLUS2-PIX/WuKong_Forest0/build/RDC/WuKong_Forest1.rdc --eid <测试EID> --out D:/UGit/renderdoc/RenderDocExtract/Output --test-log D:/UGit/renderdoc/RenderDocExtract/Tests/extract_textures_eid_<EID>.json
```

通过标准：DDS 能导出；重复运行同一 EID 不重复写同一贴图；slot/stage/resourceId 记录完整。

### 5.5 `extract_buffers.py` - 第五优先级

职责：提取 ConstantBuffer、StructuredBuffer、UniformBuffer、ByteAddressBuffer 等。

核心流程：
1. 对 VS/PS 分别读取：
   - `pipe.GetConstantBlocks(stage, onlyUsed=True)`
   - `pipe.GetReadOnlyResources(stage, onlyUsed=True)` 中 `ShaderResource.isTexture == false` 的 buffer
   - `pipe.GetReadWriteResources(stage, onlyUsed=True)` 中的 buffer
2. ConstantBuffer：
   - 用 `ShaderReflection.constantBlocks[access.index]` 获取变量布局。
   - 用 `UsedDescriptor.descriptor.resource/byteOffset/byteSize` 确定 raw range。
   - 保存 raw `.bin`。
   - 调 `GetCBufferVariableContents(pipeline, shader, stage, entry, cbufslot, buffer, offset, length)` 输出解析后的 `ShaderVariable` tree。
   - 记录每个变量的 `ShaderConstant.byteOffset/type/rows/columns/arrayByteStride/matrixByteStride`，保证可用 “shader block + variable path + byte offset/index” 回查值。
3. Structured/Uniform/ByteAddress buffer：
   - 保存 descriptor 指定 byte range，而不是盲目保存全 buffer。
   - 记录 `descriptor.byteOffset`, `byteSize`, `elementByteSize`, `bufferStructCount`, `ShaderResource.variableType`。
   - 如果 shader reflection 能给 struct members，则写出 element schema；否则仅保证 raw bytes + binding/index 准确。
4. 对 root constants / inline data / specialization constants：`ConstantBlock.bufferBacked == false` 或 `inlineDataBytes == true` 时，不强行找 buffer，记录为 inline constant 并保存解析 JSON。

单脚本测试：
```bash
python D:/UGit/renderdoc/RenderDocExtract/Scripts/extract_buffers.py --rdc D:/PTGameDoc/TLUS2/Pix/TLUS2-PIX/WuKong_Forest0/build/RDC/WuKong_Forest1.rdc --eid <测试EID> --out D:/UGit/renderdoc/RenderDocExtract/Output --test-log D:/UGit/renderdoc/RenderDocExtract/Tests/extract_buffers_eid_<EID>.json
```

通过标准：至少能导出 CB raw 与 decoded JSON；descriptor byte range 与变量 offset 可回查；重复运行去重有效。

### 5.6 `extract_mesh.py` - 第六优先级

职责：从 VS Input/Input Assembler 侧导出 Mesh。

核心流程：
1. 使用 `ActionDescription` 的 `numIndices/baseVertex/indexOffset/vertexOffset/instanceOffset/numInstances/flags`。
2. 使用 `pipe.GetIBuffer()`, `pipe.GetVBuffers()`, `pipe.GetVertexInputs()` 构建 attribute stream。
3. 若 `numInstances > 1`，只提取第一个 instance：`extracted_instance=0`；per-instance attribute 使用 `instanceOffset` 对应的第一个 instance 数据，manifest 保留原始 `numInstances`。
4. 仅当存在有效 position-like attribute 且非纯 VertexID/vertex pulling 时导出 OBJ。
5. 读取 index/vertex buffer 切片：`GetBufferData(resourceId, offset, length)`。
6. 单位转换：`--unit m` 不缩放，`--unit cm` 乘 100，记录 `unit_scale`。
7. OBJ 写入 position/normal/uv 的最佳匹配；所有 attribute 原始值写入 `attributes.bin`，布局写入 `attributes.json`；同时写出 `mesh.json` 作为无损 mesh manifest。
8. GLB/glTF 作为推荐交换格式：第一版可先不实现，但 `extract_mesh.py` 的数据结构必须为后续 GLB 导出预留字段；当实现 GLB 时，尽量写入 POSITION/NORMAL/TANGENT/TEXCOORD/COLOR/JOINTS/WEIGHTS 及 `_CUSTOM_*` attributes。
9. FBX 只作为可选后处理，不作为默认输出和去重依据。
10. mesh 去重 hash = draw index range + index bytes + all used vertex buffer slices + vertex input layout + unit。

单脚本测试：
```bash
python D:/UGit/renderdoc/RenderDocExtract/Scripts/extract_mesh.py --rdc D:/PTGameDoc/TLUS2/Pix/TLUS2-PIX/WuKong_Forest0/build/RDC/WuKong_Forest1.rdc --eid <测试EID> --out D:/UGit/renderdoc/RenderDocExtract/Output --unit cm --test-log D:/UGit/renderdoc/RenderDocExtract/Tests/extract_mesh_eid_<EID>.json
```

通过标准：传统 input mesh 能导出 OBJ + attributes sidecar + `mesh.json`；EID `7955` 的 instanced Draw 必须记录 `numInstances` 与 `extracted_instance=0`；Vertex Pulling 场景必须明确标记 `unsupported_vertex_pulling`，不能静默生成错误 OBJ。GLB 可在第一版后续补充；FBX 不作为本阶段默认门禁。

### 5.7 `build_draw_manifest.py` - 第七优先级

职责：合成 EID 级 JSON。

必须记录：
- capture 信息：rdc path、API、frame、EID、actionId、draw name、draw flags、draw params。
- pipeline：topology、viewports、scissors、raster/depth/stencil 简要状态。
- VS/PS shader library id、entry、raw/disasm/hlsl 路径。
- texture bindings：stage、slot/index、arrayElement、shader resource name、resourceId、viewId、texture library id、sampler state。
- buffer bindings：stage、slot/index、buffer library id、descriptor range、变量/schema。
- mesh library id 或 unsupported reason。
- RT/depth：resourceId、format、width/height、mip/slice、write mask。
- blend：`pipe.GetColorBlends()` 原始字段；分类字段 `opaque/masked_or_alpha_test/alpha_blend/unknown`。

Blend 分类规则：
- `blend.enabled == false`：`opaque_or_masked_candidate`。
- `blend.enabled == true` 且 src/dst blend 含 alpha 组合：`alpha_blend`。
- Masked 无法仅从 BlendState 可靠判定；需结合 PS HLSL/disasm 是否存在 `discard/clip`，若存在则标记 `masked`，否则 `opaque`。

单脚本测试：
```bash
python D:/UGit/renderdoc/RenderDocExtract/Scripts/build_draw_manifest.py --eid <测试EID> --out D:/UGit/renderdoc/RenderDocExtract/Output --test-log D:/UGit/renderdoc/RenderDocExtract/Tests/build_manifest_eid_<EID>.json
```

通过标准：draw manifest 能引用已经导出的 shader/texture/buffer/mesh library id；路径存在；JSON schema 可被验证脚本读取。

### 5.8 `extract_eid.py` - 最后集成

职责：总控脚本，只编排，不承担具体解析逻辑。

输入：
```bash
python D:/UGit/renderdoc/RenderDocExtract/Scripts/extract_eid.py --rdc D:/PTGameDoc/TLUS2/Pix/TLUS2-PIX/WuKong_Forest0/build/RDC/WuKong_Forest1.rdc --eid <测试EID> --out D:/UGit/renderdoc/RenderDocExtract/Output --unit cm --only-used true
```

输出：
- `Output/draws/eid_<EID>/draw_manifest.json`
- 更新各资产库 JSON
- 调用 shader/texture/buffer/mesh/manifest 子模块

通过标准：一键跑完整链路；重复运行不重复导出已存在资产；所有 warning 收敛在 `extraction_log.json`。

### 5.9 `validate_extraction.py` - 最终验证

职责：验证资产库和 draw manifest 的一致性。

检查项：
- manifest 引用的文件都存在。
- texture/shader/mesh/buffer hash 与文件内容一致。
- draw 中 VS/PS slot 与 shader reflection index 可对应。
- CB raw byte range 与 decoded variable offset 不越界。
- 重复运行同一 EID 后资产数量不增加。

## 6. JSON Schema 摘要

### 6.1 `texture_library.json`

```json
{
  "version": 1,
  "items": {
    "tex_<hash>": {
      "file": "textures/BC7_UNORM_SRGB_000001.dds",
      "sha256": "...",
      "format": "BC7_UNORM_SRGB",
      "width": 4096,
      "height": 2048,
      "depth": 1,
      "mips": 12,
      "arraysize": 1,
      "resource_ids_seen": ["..."]
    }
  }
}
```

### 6.2 `shader_library.json`

```json
{
  "items": {
    "shader_<hash>": {
      "stage": "VS",
      "encoding": "DXBC",
      "entry": "main",
      "raw_file": "VS_<hash>.dxbc",
      "disasm_file": "VS_<hash>.disasm.txt",
      "hlsl_file": "VS_<hash>.hlsl",
      "input_signature": [],
      "output_signature": [],
      "constant_blocks": [],
      "read_only_resources": [],
      "read_write_resources": []
    }
  }
}
```

### 6.3 `mesh_library.json`

```json
{
  "items": {
    "mesh_<hash>": {
      "obj_file": "mesh_<hash>.obj",
      "attributes_json": "mesh_<hash>.attributes.json",
      "attributes_bin": "mesh_<hash>.attributes.bin",
      "unit": "cm",
      "topology": "TriangleList",
      "num_indices": 12345,
      "attributes": []
    }
  }
}
```

### 6.4 `buffer_library.json`

```json
{
  "items": {
    "buffer_<hash>": {
      "file": "buffer_<hash>.bin",
      "sha256": "...",
      "resource_id": "...",
      "byte_offset": 0,
      "byte_size": 256,
      "element_byte_size": 16,
      "schema": {},
      "decoded_variables_file": "cbuffer_<hash>.json"
    }
  }
}
```

### 6.5 `draw_manifest.json`

```json
{
  "version": 1,
  "eid": 10891,
  "action": {},
  "pipeline": {},
  "shaders": {"vs": "shader_<hash>", "ps": "shader_<hash>"},
  "mesh": {"id": "mesh_<hash>", "status": "ok"},
  "textures": [],
  "buffers": [],
  "render_targets": [],
  "depth_target": {},
  "blend_state": {"raw": [], "classification": "opaque"},
  "warnings": []
}
```

## 7. 是否需要修改 RenderDoc 源码的判断

第一轮实现不改源码。只有以下情况验证失败后，再考虑扩展 `renderdoccmd` 或 Replay API：

1. Python API 无法稳定取得 descriptor access 的 `onlyUsed` 结果，导致大量未使用资源误导提取。
2. 某些 D3D12/Vulkan bindless descriptor 的 shader reflection index 与实际 descriptor heap offset 无法可靠关联。
3. `ShaderReflection.rawBytes` 不足以喂给 hlsl_decompiler，需要 C++ 层导出原始 DXBC/DXIL container 或 debug blob。
4. `GetCBufferVariableContents` 对 root constants / inline constants / dynamic offset 场景返回不完整。
5. Mesh input 对特定 API 的 offset/stride 解释与 BufferViewer 不一致，需要复用或暴露 BufferViewer 内部逻辑。

候选源码改动位置：
- `renderdoccmd/renderdoccmd.cpp`：新增 `extract-eid` 命令。
- `renderdoc/api/replay/renderdoc_replay.h` + `renderdoc/replay/replay_controller.cpp`：如确需新增批量导出或更直接的 DrawResourceManifest API。
- API-specific replay/debug：D3D12/Vulkan descriptor 或 buffer 特殊情况只在证明确有缺口后修改。

## 8. 正确性风险与验证策略

| 风险 | 影响 | 验证 |
|---|---|---|
| Descriptor aliasing/bindless | 错提或漏提资源 | 记录 `DescriptorAccess + Descriptor + ShaderResource` 三者；对比 RenderDoc Pipeline Viewer |
| Texture hash 不稳定 | 重复导出或误去重 | 以最终 DDS bytes + format/dimensions 做 hash；保存 source metadata |
| Masked 判定不可靠 | Opaque/Masked 混淆 | BlendState 只能判 AlphaBlend；Masked 需扫描 PS `discard/clip` |
| OBJ/FBX 无法稳定保存全部自定义属性 | 后续 UE/二次加工丢数据 | 无损 `mesh.json + attributes.bin` 作为权威；OBJ 预览；GLB 推荐交换；FBX 仅可选 |
| Vertex Pulling | 无传统 VS input mesh | 标记 unsupported，同时保存相关 buffer，后续由 shader/自定义解析恢复 |
| CBuffer 变量值偏移 | 材质参数错误 | 同时保存 raw bytes、ShaderConstant offset/type、GetCBufferVariableContents 解码结果 |
| hlsl_decompiler 失败 | 无 HLSL | raw + disasm 必须保底；HLSL 失败写入 warning |
| 多 API 通用性 | D3D11/D3D12/Vulkan 差异 | 优先 PipeState 通用接口；保留 API-specific raw 字段 |
| 测试跳步 | 后续错误叠加难排查 | 每个脚本必须测试通过才能继续；失败写入 `踩坑.md` |

## 9. 实施顺序

严格按以下顺序开发，不能跳步：

1. 初始化 `RenderDocExtract/` 目录、复制计划、创建 `踩坑.md`。
2. `rd_session.py`：打开 RDC、列 Draw、定位 EID；测试通过；更新 `开发状态.md`。
3. `library_db.py`：JSON DB 与 hash 去重；测试通过；更新 `开发状态.md`。
4. `extract_shaders.py`：raw/disasm/HLSL/signature 去重；测试通过；更新 `开发状态.md`；**停下等待用户确认 shader 文件夹输出，确认后才能继续**。
5. `extract_textures.py`：VS/PS texture slot、DDS 导出、texture library 去重；测试通过；更新 `开发状态.md`；**停下等待用户确认 texture 输出，确认后才能继续**。
6. `extract_buffers.py`：CB/Structured/Uniform raw range、变量 schema、decoded JSON；测试通过；更新 `开发状态.md`；**停下等待用户确认 buffer 输出，确认后才能继续**。
7. `extract_mesh.py`：传统 VS input mesh OBJ + attributes sidecar；测试通过；更新 `开发状态.md`；**停下等待用户确认 mesh 输出，确认后才能继续**。
8. `build_draw_manifest.py`：合成 draw_manifest；测试通过；更新 `开发状态.md`；**停下等待用户确认 manifest 输出，确认后才能继续**。
9. `extract_eid.py`：一键总控集成；对 EID `7643` 和 `7955` 都测试通过；更新 `开发状态.md`。
10. `validate_extraction.py`：完整一致性验证；对 EID `7643` 和 `7955` 都测试通过。
11. 用固定 EID `7643`、`7955` 以及后续用户指定真实 EID 跑通后，再判断是否需要 C++/renderdoccmd 扩展。

## 10. 本阶段预计新增/维护文件

新增/维护：

- `D:/UGit/renderdoc/RenderDocExtract/Plan/RenderDoc_EID_Draw_Resource_Extractor_Plan.md`
- `D:/UGit/renderdoc/RenderDocExtract/Plan/踩坑.md`
- `D:/UGit/renderdoc/RenderDocExtract/Plan/开发状态.md`
- `D:/UGit/renderdoc/RenderDocExtract/Scripts/rd_session.py`
- `D:/UGit/renderdoc/RenderDocExtract/Scripts/library_db.py`
- `D:/UGit/renderdoc/RenderDocExtract/Scripts/extract_eid.py`
- `D:/UGit/renderdoc/RenderDocExtract/Scripts/extract_textures.py`
- `D:/UGit/renderdoc/RenderDocExtract/Scripts/extract_shaders.py`
- `D:/UGit/renderdoc/RenderDocExtract/Scripts/extract_mesh.py`
- `D:/UGit/renderdoc/RenderDocExtract/Scripts/extract_buffers.py`
- `D:/UGit/renderdoc/RenderDocExtract/Scripts/build_draw_manifest.py`
- `D:/UGit/renderdoc/RenderDocExtract/Scripts/validate_extraction.py`
- `D:/UGit/renderdoc/RenderDocExtract/Tests/*.json`
- `D:/UGit/renderdoc/RenderDocExtract/Logs/*.log`
- `D:/UGit/renderdoc/RenderDocExtract/Output/**`

暂不修改：
- `D:/UGit/renderdoc/renderdoccmd/renderdoccmd.cpp`
- `D:/UGit/renderdoc/renderdoc/api/replay/renderdoc_replay.h`
- `D:/UGit/renderdoc/renderdoc/replay/replay_controller.cpp`
