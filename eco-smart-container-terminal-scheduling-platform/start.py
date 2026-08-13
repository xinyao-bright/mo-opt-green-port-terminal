import os
import sys
import time
import webbrowser
from threading import Timer

def open_browser():
    time.sleep(3)
    webbrowser.open('http://localhost:5000')

def main():
    print("=" * 60)
    print("港口调度系统 - 启动中...")
    print("=" * 60)

    # 检查是否在正确的目录
    if not os.path.exists('app.py'):
        print("❌ 错误: 请在 modified_project 目录中运行此脚本")
        print("   cd modified_project")
        print("   python start.py")
        sys.exit(1)

    # 检查依赖
    try:
        import flask
        import flask_login
        import flask_sqlalchemy
        print("所有依赖已安装")
    except ImportError as e:
        print(f"缺少依赖: {e}")
        print("\n请运行: pip install -r requirements.txt")
        sys.exit(1)

    # 启动浏览器定时器
    Timer(3.0, open_browser).start()

    print("\n启动服务器...")
    print("   地址: http://localhost:5000")
    print("   按 Ctrl+C 停止服务器")
    print("\n" + "=" * 60)

    # 导入并运行Flask应用
    from app import app
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)

if __name__ == '__main__':
    main()
