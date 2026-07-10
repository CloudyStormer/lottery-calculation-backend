# 数研选号后端

FastAPI 服务，负责从中国体彩网和中国福彩网的公开官方页面/接口同步历史开奖，缓存到 SQLite，并针对不同号码结构生成三组统计候选。

## 首版覆盖

- 体彩：超级大乐透、排列3、排列5、7星彩
- 福彩：双色球、福彩3D、七乐彩、快乐8（选一至选十）

竞猜型彩票依赖实时比赛、赔率和伤停等外部信息；即开型彩票不存在下一期开奖，因此二者不进入历史号码生成器。

## 本地启动

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

接口文档：<http://localhost:8000/docs>

首次生成某个玩法时，服务会同步该玩法最近最多 `LOTTERY_HISTORY_LIMIT` 期历史数据。默认值为1200，可通过环境变量调整。也可以调用：

```bash
curl -X POST 'http://localhost:8000/api/v1/games/dlt/sync?full=true'
```

抓取完整的官网可用历史。生产环境应保持低频增量更新，并保留 SQLite 数据卷。

## 数学边界

模型包含多尺度滚动窗口、贝叶斯收缩、严格时序回测、Brier损失、均匀性/熵/自相关诊断和正则化共现项。若滚动窗口不能稳定击败等概率基线，模型会主动向均匀分布收缩。

候选的“评分指数”只用于比较同一次生成中的候选，不是中奖概率。公平随机开奖下，不存在仅凭历史数据保证预测下一期结果的方法。

## 测试

```bash
pytest
ruff check .
```
