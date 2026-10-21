<h1>cds-cli</h1>

## Install

```bash
# SMB 挂载盘上的项目应将虚拟环境放在本地磁盘。
uv sync
```

## Configure
get your api <https://cds.climate.copernicus.eu/profile>

```bash
cat ~/.cdsapirc
url: https://cds.climate.copernicus.eu/api
key: <PERSONAL-ACCESS-TOKEN>
```

## 使用
```bash
sublimt.py   #提交任务
cds status --status accepted,running,successful #查看任务状态
cds fetch    # 拉取下载的url
cds monitor  # 开始下载文件
```
