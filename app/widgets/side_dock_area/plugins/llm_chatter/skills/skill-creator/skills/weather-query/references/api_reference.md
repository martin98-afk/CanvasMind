# OpenWeatherMap API 参考

## API 端点

### 1. 当前天气数据

**端点**: `https://api.openweathermap.org/data/2.5/weather`

**参数**:
| 参数 | 必填 | 说明 |
|------|------|------|
| q | 是 | 城市名（支持中文） |
| appid | 是 | API Key |
| units | 否 | 单位制式：metric(摄氏度), imperial(华氏度), standard(开尔文) |
| lang | 否 | 语言：zh_cn(中文), en(英文) |

**响应示例**:
```json
{
  "name": "Beijing",
  "weather": [{"main": "Clear", "description": "晴朗"}],
  "main": {"temp": 25.5, "feels_like": 26.2, "humidity": 60},
  "wind": {"speed": 3.5}
}
```

### 2. 天气预报数据

**端点**: `https://api.openweathermap.org/data/2.5/forecast`

**参数**: 与当前天气 API 相同

**响应**: 每 3 小时一次预报，最多 5 天数据

### 3. 空气质量数据

**端点**: `http://api.openweathermap.org/data/2.5/air_pollution`

**参数**:
| 参数 | 必填 | 说明 |
|------|------|------|
| lat | 是 | 纬度 |
| lon | 是 | 经度 |
| appid | 是 | API Key |

**AQI 等级**:
| AQI | 等级 | 说明 |
|-----|------|------|
| 1 | 优 | 空气质量令人满意 |
| 2 | 良 | 空气质量可接受 |
| 3 | 轻度污染 | 敏感人群应减少户外活动 |
| 4 | 中度污染 | 所有人应减少户外活动 |
| 5 | 重度污染 | 所有人应避免户外活动 |

## 错误码

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 401 | API Key 无效 |
| 404 | 城市未找到 |
| 429 | 请求超限 |
| 500 | 服务器错误 |

## 使用限制

- 免费计划：60 次/分钟
- 新 API Key 激活时间：10-30 分钟
