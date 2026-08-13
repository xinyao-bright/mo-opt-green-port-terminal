# 港口调度系统 - 快速启动指南

## 系统功能

✅ **已完成的核心功能**：

1. **用户认证系统**
   - 用户注册和登录
   - 密码哈希加密（pbkdf2:sha256）
   - Session管理
   - 用户数据隔离

2. **主题切换系统**
   - 暗黑模式（默认）
   - 明亮模式
   - 海洋蓝主题
   - 主题设置自动保存

3. **国际化（i18n）系统**
   - 简体中文（默认）
   - English
   - 动态语言切换
   - 语言设置自动保存

4. **泊位配置管理**
   - 创建/编辑/删除配置
   - 动态泊位设置
   - 岸桥参数配置
   - 配置激活功能

5. **历史记录管理**
   - 调度历史查看
   - 方案详情展示
   - 历史记录删除

6. **数据库持久化**
   - SQLite数据库
   - 用户、船舶、配置、历史记录完整持久化

## 安装步骤

### 1. 安装依赖
```bash
cd modified_project
pip install -r requirements.txt
```

### 2. 启动服务器
```bash
python app.py
```

服务器将在 http://localhost:5000 启动

## 测试流程

### 第一步：用户注册
1. 访问 http://localhost:5000
2. 系统自动跳转到登录页
3. 点击"立即注册"
4. 填写信息：
   - 用户名：testuser（3-80字符，字母数字下划线）
   - 邮箱：test@example.com
   - 密码：test123（至少6字符，含字母和数字）
5. 点击"注册"

### 第二步：登录系统
1. 注册成功后自动跳转到登录页
2. 输入用户名和密码
3. 可选择"记住我"
4. 点击"登录"

### 第三步：测试主题切换
1. 登录后在右上角找到主题选择器
2. 切换三个主题：
   - 暗黑模式（默认）
   - 明亮模式
   - 海洋蓝
3. 刷新页面验证主题保持

### 第四步：测试语言切换
1. 右上角找到语言选择器
2. 切换"简体中文" ↔ "English"
3. 观察所有界面文本变化
4. 刷新页面验证语言保持

### 第五步：创建泊位配置
1. 点击导航栏"泊位配置"
2. 点击"创建新配置"
3. 填写配置信息：
   - 配置名称：测试配置
   - 泊位总数：17
   - 岸桥总数：30
   - 岸桥效率：48
4. 点击"添加泊位"添加泊位详情
5. 点击"保存"
6. 点击"激活此配置"

### 第六步：查看历史记录
1. 点击导航栏"历史记录"
2. 查看调度历史列表
3. 点击"查看详情"查看方案详情
4. 测试删除功能

## 目录结构

```
modified_project/
├── app.py                    # Flask主应用（已完成）
├── models.py                 # 数据库模型（已完成）
├── auth.py                   # 认证逻辑（已完成）
├── requirements.txt          # Python依赖（已完成）
├── database.db              # SQLite数据库（自动创建）
├── templates/
│   ├── base.html            # 基础模板（已完成）
│   ├── login.html           # 登录页面（已完成）
│   ├── register.html        # 注册页面（已完成）
│   ├── port_config.html     # 泊位配置（已完成）
│   ├── history.html         # 历史记录（已完成）
│   └── index.html           # 主页面（待重构）
└── static/
    ├── css/
    │   ├── themes.css       # 主题样式（已完成）
    │   ├── auth.css         # 认证页面样式（已完成）
    │   ├── navigation.css   # 导航样式（已完成）
    │   └── style.css        # 主样式（待重构）
    ├── js/
    │   ├── theme.js         # 主题管理（已完成）
    │   ├── i18n.js          # 国际化（已完成）
    │   ├── port_config.js   # 泊位配置（已完成）
    │   ├── history.js       # 历史记录（已完成）
    │   └── script.js        # 主脚本（待优化）
    └── i18n/
        ├── zh-CN.json       # 中文翻译（已完成）
        └── en.json          # 英文翻译（已完成）
```

## API端点

### 认证相关
- `GET/POST /login` - 登录
- `GET/POST /register` - 注册
- `GET /logout` - 登出

### 船舶管理
- `GET /api/ships` - 获取船舶列表
- `POST /api/ships/import` - 导入CSV
- `POST /api/ships/clear` - 清空船舶池

### 泊位配置
- `GET /api/port-config` - 获取配置列表
- `POST /api/port-config` - 创建配置
- `POST /api/port-config/<id>/activate` - 激活配置
- `DELETE /api/port-config/<id>` - 删除配置

### 调度算法
- `POST /api/schedule` - 运行调度算法

### 历史记录
- `GET /api/history` - 获取历史列表
- `GET /api/history/<id>` - 获取历史详情
- `DELETE /api/history/<id>` - 删除历史记录

## 待完成工作

1. **重构index.html**
   - 继承base.html模板
   - 集成主题和i18n系统
   - 优化布局结构

2. **优化script.js**
   - 添加i18n调用
   - 增强Pareto方案展示
   - 集成主题系统

3. **重构style.css**
   - 使用CSS变量替换硬编码颜色
   - 确保主题切换正常工作

## 技术栈

- **后端**：Flask 3.0.0 + Flask-Login + Flask-SQLAlchemy
- **数据库**：SQLite 3
- **前端**：Bootstrap 5.3.0 + Vanilla JavaScript
- **算法**：NSGA-II多目标优化
- **安全**：Werkzeug密码哈希

## 注意事项

1. **生产环境**：修改`app.py`中的`SECRET_KEY`
2. **数据库**：首次运行会自动创建`database.db`
3. **端口冲突**：如5000端口被占用，修改`app.py`最后一行的`port`参数
4. **浏览器兼容**：建议使用现代浏览器（Chrome, Firefox, Edge）

## 故障排除

### 1. 导入错误
```bash
ModuleNotFoundError: No module named 'flask_login'
```
**解决方案**：运行 `pip install -r requirements.txt`

### 2. 数据库错误
```bash
sqlalchemy.exc.OperationalError: no such table
```
**解决方案**：删除`database.db`文件，重新启动应用

### 3. 端口被占用
```bash
OSError: [Errno 48] Address already in use
```
**解决方案**：修改`app.py`中的端口号或关闭占用5000端口的进程

## 下一步

完成当前系统后，可以继续实现：
- 数据导出（Excel/PDF）
- 更多图表可视化
- 移动端优化
- 更多语言支持
- WebSocket实时更新
