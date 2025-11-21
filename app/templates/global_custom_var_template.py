PARAMETER_TEMPLATE = {
    "大模型配置": {
        "模型名称": "gpt-4",
        "API_URL": "https://api.openai.com/v1/chat/completions",
        "API_KEY": "",
        "温度": 0.7,
        "最大Token": 2048,
        "系统提示": ""
    },
    "数据库配置": {
        "主机": "localhost",
        "端口": 3306,
        "用户名": "root",
        "密码": "",
        "数据库名": "mydb"
    },
    "HTTP请求配置": {
        "基础URL": "https://api.example.com",
        "请求方法": "POST",
        "请求头Content-Type": "application/json",
        "请求头Authorization": "Bearer ",
        "超时时间(秒)": 30,
        "重试次数": 3,
        "默认请求参数": {}
    },
    "文件存储配置": {
        "存储路径": "./uploads",
        "最大文件大小(MB)": 10,
        "允许的文件类型": "txt,pdf,png,jpg,jpeg,gif",
        "访问URL前缀": "https://yourdomain.com/files"
    },
    "消息队列配置 (RabbitMQ)": {
        "主机": "localhost",
        "端口": 5672,
        "用户名": "guest",
        "密码": "guest",
        "虚拟主机": "/",
        "队列名称": "default_queue"
    },
    "消息队列配置 (Redis)": {
        "Redis主机": "localhost",
        "Redis端口": 6379,
        "Redis密码": "",
        "队列键名": "message_queue"
    },
    "缓存配置 (Redis)": {
        "Redis主机": "localhost",
        "Redis端口": 6379,
        "Redis密码": "",
        "数据库索引": 0,
        "默认过期时间(秒)": 3600
    },
    "日志配置": {
        "日志级别": "INFO", # 例如: DEBUG, INFO, WARNING, ERROR
        "日志文件路径": "./logs/app.log",
        "日志文件最大大小(MB)": 10,
        "日志文件保留数量": 5,
        "是否输出到控制台": True
    },
    "定时任务配置 (Cron)": {
        "表达式": "0 0 * * *", # 例如: 每天零点执行
        "任务描述": "每日数据备份",
        "执行脚本路径": "/path/to/script.py"
    },
    "图像处理配置": {
        "目标宽度": 1920,
        "目标高度": 1080,
        "质量(1-100)": 90,
        "格式": "JPEG", # 例如: JPEG, PNG, WEBP
        "是否压缩": True
    },
    "机器学习模型配置 (通用)": {
        "模型路径": "/path/to/model.pkl",
        "特征列": ["feature1", "feature2"],
        "目标列": "target",
        "训练数据路径": "/path/to/train.csv",
        "测试数据路径": "/path/to/test.csv"
    },
    "API限流配置": {
        "限流窗口(秒)": 60,
        "窗口内最大请求数": 100,
        "限流策略": "sliding_window", # 例如: fixed_window, sliding_window, token_bucket
        "超出限制响应码": 429
    },
    "数据源配置 (CSV)": {
        "文件路径": "/path/to/data.csv",
        "分隔符": ",",
        "编码": "utf-8",
        "是否包含表头": True,
        "日期列": ["date_column"] # 指定需要解析为日期的列
    },
    "数据源配置 (Excel)": {
        "文件路径": "/path/to/data.xlsx",
        "工作表名称": "Sheet1",
        "是否包含表头": True,
        "日期列": ["date_column"]
    },
    "数据源配置 (JSON)": {
        "文件路径": "/path/to/data.json",
        "根级数据路径": "$.data", # 使用JSONPath
        "编码": "utf-8"
    },
    "FTP/SFTP配置": {
        "主机": "ftp.example.com",
        "端口": 22, # SFTP通常用22, FTP用21
        "用户名": "username",
        "密码": "",
        "远程路径": "/remote/path/",
        "本地路径": "/local/path/",
        "是否使用SFTP": True
    },
    "搜索引擎配置 (Elasticsearch)": {
        "主机": "localhost",
        "端口": 9200,
        "用户名": "",
        "密码": "",
        "索引名称": "default_index"
    }
}