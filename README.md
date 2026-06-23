# VulnBot RAG 渗透测试任务运行说明

如何使用已经跑通的 RAG 知识库，让 VulnBot 完整执行一次授权渗透测试任务。

当前工作流默认使用 RAG：VulnBot 会在制定计划、细化任务、更新计划时，从 `pentest_notes` 知识库检索本地资料，再把检索结果加入 LLM 上下文。命令仍然通过 Kali SSH 实际执行。

> 仅在你拥有明确授权的靶场、实验环境或目标系统中使用本项目。

## 1. 总体流程

一次完整的 RAG 渗透测试任务包含这些环节：

1. 启动 Milvus 向量数据库。
2. 配置 LLM、embedding、Kali SSH 和 RAG 知识库。
3. 初始化项目数据库。
4. 启动知识库 API 和 WebUI。
5. 上传 RAG 文档并确认检索成功。
6. 启动 `cli.py vulnbot`。
7. 输入授权目标和测试目标。
8. VulnBot 结合 RAG 知识库制定计划、执行 Kali 命令、更新计划。
9. 结束后保存 session，便于后续继续分析。

## 2. 准备 Python 环境

当前项目使用 Python 3.11 和本地虚拟环境 `.venv`。以下命令都按 Windows CMD 写法给出。

如果 `.venv` 已存在，安装依赖：

```bat
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

如果 `.venv` 不存在，先创建：

```bat
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

如果你已安装 CUDA 版 PyTorch，避免后续 `pip install -r requirements.txt` 又覆盖为 CPU 版。需要重新安装 GPU 版时可使用：

```bat
.\.venv\Scripts\python.exe -m pip install --no-cache-dir torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu124
```

检查 GPU 是否可用：

```bat
.\.venv\Scripts\python.exe -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.version.cuda); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'no gpu')"
```

默认情况下，RAG embedding 会自动选择设备：检测到 CUDA 时使用 GPU，否则回退 CPU。多 GPU/大显存服务器通常直接使用默认设置即可。

如果在 Windows 本地或小显存机器上遇到 CUDA OOM/native DLL 崩溃，可以临时强制 embedding 使用 CPU：

```bat
set VULNBOT_EMBEDDING_DEVICE=cpu
```

如需强制完全屏蔽 CUDA：

```bat
set CUDA_VISIBLE_DEVICES=-1
```

## 3. 配置 LLM 与 Embedding

编辑 `model_config.yaml`：

```yaml
llm_model: openai
base_url: https://api.deepseek.com
llm_model_name: deepseek-v4-flash
api_key: "your-api-key"
api_key_env: ""
embedding_models: maidalun1020/bce-embedding-base_v1
embedding_type: local
embedding_url: ""
rerank_model: maidalun1020/bce-reranker-base_v1
temperature: 0
history_len: 5
timeout: 600
context_length: 120000
```

关键参数：
- `llm_model`：OpenAI 兼容接口使用 `openai`。
- `base_url`：LLM API 地址。
- `llm_model_name`：LLM 模型名。
- `api_key`：API Key。也可留空并改用 `api_key_env`。
- `api_key_env`：环境变量名，不是密钥本身。
- `embedding_models`：本地 embedding 模型，用于文档向量化和查询向量化。
- `embedding_type`：当前使用 `local`，表示本地 HuggingFace embedding。
- `rerank_model`：检索后重排模型。
- `temperature`：建议为 `0`，让计划和命令更稳定。
- `timeout`：LLM 请求超时时间。

使用环境变量保存密钥时：

```bat
set DEEPSEEK_API_KEY=your-api-key
```

并配置：

```yaml
api_key: ""
api_key_env: "DEEPSEEK_API_KEY"
```

检查 LLM：

```bat
.\.venv\Scripts\python.exe scripts\check_llm_connection.py
```

期待看到：

```text
[OK] LLM request succeeded.
```

## 4. 配置 RAG、Milvus 和 Kali

编辑 `basic_config.yaml`：

```yaml
log_verbose: true
enable_rag: true
mode: semi
KB_ROOT_PATH: E:/cursor_project/VulnBot-main/data/knowledge_base
http_default_timeout: 300
kali:
  hostname: 127.0.0.1
  port: 2222
  username: kali
  password: kali
api_server:
  host: 127.0.0.1
  port: 7861
  public_host: 127.0.0.1
  public_port: 7861
webui_server:
  host: 127.0.0.1
  port: 8501
```

关键参数：
- `enable_rag: true`：必须开启。关闭后 VulnBot 不会检索知识库。
- `mode: semi`：当前主流程会生成并执行远程命令。
- `kali.hostname` / `kali.port`：Kali SSH 地址和端口。
- `kali.username` / `kali.password`：Kali SSH 凭据。
- `api_server`：知识库 API 地址。
- `webui_server`：知识库 WebUI 地址。

编辑 `kb_config.yaml`：
```yaml
default_vs_type: milvus
milvus:
  uri: "http://127.0.0.1:19530"
  user: ""
  password: ""
kb_name: "pentest_notes"
chunk_size: 750
overlap_size: 150
top_n: 1
top_k: 3
score_threshold: 0.5
```

关键参数：

- `milvus.uri`：Milvus 服务地址。
- `kb_name`：VulnBot 主流程检索的知识库名称，必须和 WebUI 创建的知识库同名。
- `chunk_size`：文档切片长度。
- `overlap_size`：相邻切片重叠长度。
- `top_k`：从 Milvus 初始召回的片段数量。
- `top_n`：rerank 后保留的片段数量。
- `score_threshold`：相似度阈值。

Kali 环境要求：

- Kali 已启动并可 SSH 登录。
- Kali 能访问授权目标。
- Kali 中已有常用工具，例如 `nmap`、`curl`、`gobuster`、`msfconsole` 等。

注意：当前远程 shell 禁用了 `apt`、`apt-get`，避免任务过程中修改环境依赖。

## 5. 启动 Milvus

本仓库提供了本地 Milvus Compose 文件：
```text
docker-compose.milvus.yml
```

启动：
docker compose -f docker-compose.milvus.yml up -d


检查：
.\.venv\Scripts\python.exe scripts\check_milvus_connection.py --uri http://127.0.0.1:19530

期待输出：

```text
[1/2] TCP check: 127.0.0.1:19530
[OK] TCP port is reachable
[2/2] pymilvus check: http://127.0.0.1:19530
[OK] Connected to Milvus, server version: v2.4.9
```

## 6. 初始化项目数据

首次运行前执行：

```bat
.\.venv\Scripts\python.exe cli.py init
```

运行效果：

- 创建 `data/`、`logs/` 等运行目录。
- 初始化 SQLite 数据库表。
- 生成或补齐默认配置模板。

默认数据库配置在 `db_config.yaml`：这部分需要自定义修改

```yaml
type: sqlite
sqlite:
  path: E:/cursor_project/VulnBot-main/data/vulnbot.sqlite3
```

## 7. 启动知识库 API 和 WebUI

```bat
.\.venv\Scripts\python.exe cli.py start -a
```

参数说明：

- `start`：启动知识库相关服务。
- `-a, --all`：同时启动 API 和 WebUI。
- `--api`：只启动 API，默认地址 `http://127.0.0.1:7861`。
- `-w, --webui`：只启动 WebUI，默认地址 `http://127.0.0.1:8501`。

期待效果：

- API 监听 `http://127.0.0.1:7861`。
- WebUI 监听 `http://127.0.0.1:8501`。
- CMD 窗口持续占用，这是正常现象。
- 停止服务时按 `Ctrl+C`。

## 8. 准备并上传 RAG 文档

本仓库已准备测试资料目录：

```text
E:\cursor_project\VulnBot-main\data\rag_seed\pentest_notes
```

包含：

```text
00_task_scope_template.md
README_sources.md
owasp_attack_surface_analysis.md
owasp_authentication.md
owasp_authorization.md
owasp_file_upload.md
owasp_input_validation.md
owasp_sql_injection_prevention.md
owasp_ssrf_prevention.md
owasp_wstg_information_gathering.md
owasp_wstg_testing_for_apis.md
```

资料用途：

- `00_task_scope_template.md`：授权范围模板，要求 VulnBot 只测试任务描述里明确给出的目标。
- `README_sources.md`：资料来源说明。
- `owasp_*`：OWASP WSTG 和 OWASP Cheat Sheet 资料，用于通用 Web/接口测试知识。

上传步骤：

1. 浏览器打开 `http://127.0.0.1:8501`。
2. 进入“知识库管理”。
3. 创建知识库，名称填写 `pentest_notes`。
4. 向量库类型保持 `milvus`。
5. Embeddings 模型保持默认值。
6. 在“上传知识文件”中选择上面目录里的所有 `.md` 文件。
7. 点击“添加文件到知识库”。
8. 等待文档切片、embedding 和写入 Milvus 完成。

成功后应看到：

- 文件列表出现上传的 `.md` 文件。
- `源文件`、`向量库` 列显示成功状态。
- 文档原文保存到 `data/knowledge_base/pentest_notes/content/`。
- Milvus 中出现 `pentest_notes` collection。

## 9. 验证 RAG 检索

WebUI 中已经增加了测试区域：

```text
知识库检索测试
输入检索关键词
检索知识库
```

选择 `pentest_notes` 后，输入：

```text
SQL injection
```

或：

```text
attack surface analysis
```

或：

```text
file upload
```

点击“检索知识库”。

成功结果：

- 页面显示找到的相关片段数量。
- 展开结果能看到 `page_content`。
- 来源文件可能是 `owasp_sql_injection_prevention.md`、`owasp_attack_surface_analysis.md` 等。

这表示：

```text
文档上传成功 -> embedding 成功 -> 写入 Milvus 成功 -> 检索成功
```

只有这一步成功后，再进入 VulnBot 渗透测试任务。

## 10. 运行 RAG 驱动的 VulnBot 渗透测试

确认以下服务仍在运行：

- Milvus：`127.0.0.1:19530`
- API：`127.0.0.1:7861`
- WebUI：`127.0.0.1:8501`
- Kali SSH：`basic_config.yaml` 中配置的地址和端口

启动 VulnBot：

.\.venv\Scripts\python.exe cli.py vulnbot -m 5

参数说明：

- `vulnbot`：启动交互式渗透测试主流程。
- `-m, --max_interactions`：每个角色最大交互轮数。默认 `5`。数值越大，计划、命令执行和结果分析轮数越多，LLM 调用次数也越多。

启动后会询问：

```text
Do you want to continue from a previous session? [y/N]:
```

输入：

- `y`：继续历史 session。
- 直接回车或 `n`：创建新任务。

新任务会提示：

```text
Please describe the penetration testing task.
>
```

推荐任务输入格式：

```text
Please perform an authorized penetration test against the lab target <TARGET_IP_OR_URL>. Only test this target. Use the local RAG knowledge base pentest_notes as supporting material. Start with service discovery, then prioritize web/API enumeration if HTTP or HTTPS is exposed. Verify findings through Kali commands and avoid destructive actions.
```

运行中你会看到类似：

```text
Plan Initialized.
---------- Execute Result ---------
Action:nmap ...
Observation: ...
---------- Execute Result End ---------
```

VulnBot 会自动执行：

1. 读取任务描述。
2. 从 `pentest_notes` 检索与当前任务相关的资料。
3. 用 LLM 生成角色计划。
4. 细化当前任务。
5. 生成 `<execute>...</execute>` 中的 Kali shell 命令。
6. 通过 SSH 执行命令。
7. 收集 observation。
8. 再次结合 RAG 和 observation 更新计划。
9. 在 Collector、Scanner、Exploiter 等角色之间推进。
10. 达到交互轮数或任务完成后结束。

结束时会询问保存 session：

```text
Before you quit, you may want to save the current session.
Please enter the name of the current session. (Default with current timestamp)
```
保存后：
- session 写入 SQLite 数据库。
- 执行日志写入 `logs/`。
- 下次运行 `cli.py vulnbot` 可选择继续历史 session。

## 11. 如何判断 RAG 在任务中生效

需要同时满足：

- `basic_config.yaml` 中 `enable_rag: true`。
- `kb_config.yaml` 中 `kb_name: "pentest_notes"`。
- WebUI 检索测试能返回相关片段。
- 运行 `cli.py vulnbot` 时任务描述中明确要求使用本地知识库。

代码接入点：

- `WritePlan.run()`：生成初始计划时检索知识库。
- `WritePlan.update()`：更新计划时检索知识库。
- `Planner.next_task_details()`：细化下一步任务时检索知识库。
- `_chat()`：当 `enable_rag: true` 且 `kb_name` 有值时，调用知识库检索并把结果加入 LLM 输入。

如果没有检索到相关片段，VulnBot 仍会继续运行，但会更接近普通 LLM 流程。


## 12. 最小命令清单

先准备 RAG 和基础服务：

```bat
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
docker compose -f docker-compose.milvus.yml up -d
.\.venv\Scripts\python.exe scripts\check_milvus_connection.py --uri http://127.0.0.1:19530
.\.venv\Scripts\python.exe cli.py init
.\.venv\Scripts\python.exe scripts\check_llm_connection.py
.\.venv\Scripts\python.exe cli.py start -a
```

然后在 WebUI 上传 `data\rag_seed\pentest_notes` 中的 `.md` 文件，并用“知识库检索测试”确认检索成功。

查看 AutoPenBench 中有哪些任务：

```bat
.\.venv\Scripts\python.exe scripts\autopenbench.py list --level in-vitro
.\.venv\Scripts\python.exe scripts\autopenbench.py list --level real-world
.\.venv\Scripts\python.exe scripts\autopenbench.py list
```

还可以按分类筛选，例如：

```bat
.\.venv\Scripts\python.exe scripts\autopenbench.py list --level in-vitro --category web_security
```

查看某个任务的具体目标和里程碑：

```bat
.\.venv\Scripts\python.exe scripts\autopenbench.py show autopenbench:in-vitro/access_control/vm0
```

可选：运行前做一次 preflight 检查：

```bat
.\.venv\Scripts\python.exe scripts\autopenbench.py preflight autopenbench:in-vitro/access_control/vm0
```

`preflight` 的作用是在真正跑 VulnBot 之前，快速检查任务环境是否基本可用。它不会执行渗透测试，也不会启动完整靶场流程。

它主要检查：

- LLM 配置是否可用。
- Docker Compose 是否可用。
- AutoPenBench 本地目录是否存在。
- 任务 ID 是否存在。
- 对应任务的 Compose service 是否存在。
- Kali、目标服务、依赖服务是否能在 Compose 配置中找到。

它不会检查：

- 镜像能不能完整 build。
- 外网依赖能不能下载成功。
- 靶场容器最终能不能正常运行。
- VulnBot 能不能完成任务。

所以，`preflight` 适合用来排查“任务配置和基础工具是否齐”；真正验证任务能否跑通，仍然要执行 `run`。

运行这个明确任务，完成 RAG + VulnBot + AutoPenBench 的闭环：

```bat
.\.venv\Scripts\python.exe scripts\autopenbench.py run ^
  autopenbench:in-vitro/access_control/vm0 ^
  --max-steps 24 ^
  --max-interactions 8 ^
  --timeout 3600
```

参数说明：

- `autopenbench:in-vitro/access_control/vm0`：本次指定运行的 AutoPenBench 靶场任务。
- `--max-steps 24`：整个 benchmark 的全局最大执行步数。
- `--max-interactions 8`：VulnBot 每个角色的最大交互轮数。
- `--timeout 3600`：任务最长运行时间，单位秒。

AutoPenBench 的 Docker 运行机制：

- 每次执行 `run`，都会为当前任务重置并启动一套对应的容器环境。
- 如果该任务镜像还没有构建过，`run` 会先执行 `docker compose build`。
- 构建成功后，Docker 会缓存镜像和构建层。
- 后续运行同一个任务时，可以加 `--no-build` 跳过重新构建镜像。
- 即使使用 `--no-build`，`run` 仍会先执行 `docker compose down --remove-orphans` 清理上一轮容器。
- 清理后再执行 `docker compose up -d --no-build` 启动 Kali、目标靶机和依赖服务。
- 所以：容器每次会重建/重启，但镜像不一定每次重建。

同一个任务已经成功构建过镜像后，可以这样复用镜像：

```bat
.\.venv\Scripts\python.exe scripts\autopenbench.py run ^
  autopenbench:in-vitro/access_control/vm0 ^
  --max-steps 24 ^
  --max-interactions 8 ^
  --timeout 3600 ^
  --no-build
```

`run` 会真正重置靶场、启动目标服务、运行 VulnBot、记录轨迹并评分。最小闭环只需要执行 `run`；如果你想先排查环境问题，再单独执行 `preflight`。

运行后查看报告：

```bat
.\.venv\Scripts\python.exe scripts\autopenbench.py report
```
