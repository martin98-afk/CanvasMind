# Python 安全最佳实践

## 常见安全漏洞类型

### 1. 硬编码凭证 (B105/B106)
```python
# ❌ 危险
password = "admin123"
api_key = "sk-1234567890"

# ✅ 安全
import os
password = os.environ.get("DB_PASSWORD")
api_key = os.environ.get("API_KEY")
```

### 2. SQL 注入 (B608)
```python
# ❌ 危险
query = f"SELECT * FROM users WHERE id = {user_id}"
cursor.execute(query)

# ✅ 安全
cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
```

### 3. 命令注入 (B601-B610)
```python
# ❌ 危险
os.system(f"ls {user_input}")
subprocess.call(cmd, shell=True)

# ✅ 安全
subprocess.run(["ls", user_input])
```

### 4. 不安全的反序列化 (B301)
```python
# ❌ 危险
import pickle
data = pickle.loads(user_data)

# ✅ 安全
import json
data = json.loads(user_data)
```

### 5. 弱加密算法 (B303-B308)
```python
# ❌ 危险
from Crypto.Hash import MD5
hash = MD5.new(data)

# ✅ 安全
import hashlib
hash = hashlib.sha256(data.encode())
```

### 6. 不安全的 SSL 验证 (B501)
```python
# ❌ 危险
import requests
requests.get(url, verify=False)

# ✅ 安全
requests.get(url, verify=True)
```

## Bandit 检查命令

```bash
# 递归扫描项目
bandit -r project/

# 输出 JSON 格式
bandit -r project/ -f json -o report.json

# 按严重程度过滤
bandit -r project/ -lll  # 仅高严重程度

# 跳过特定测试
bandit -r project/ -s B101
```

## 安全评分等级

| 等级 | 描述 | 响应时间 |
|------|------|----------|
| HIGH | 严重安全漏洞 | 立即修复 |
| MEDIUM | 潜在安全风险 | 尽快修复 |
| LOW | 轻微安全问题 | 计划修复 |
