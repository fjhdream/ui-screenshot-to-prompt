import requests  # 新增导入
from flask import Flask, request, jsonify
from PIL import Image
import os
import uuid
import multiprocessing
import sys
import argparse
import signal
import atexit
from gunicorn.app.base import BaseApplication
from main import process_image, set_detection_method  # 导入现有的处理函数和设置方法

app = Flask(__name__)

def generate_temp_filepath():
    """生成临时文件路径"""
    temp_dir = "temp_images"
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    return os.path.join(temp_dir, f"{uuid.uuid4()}.png")


def cleanup_temp_file(filepath):
    """清理临时文件"""
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
    except Exception as e:
        print(f"清理临时文件失败: {str(e)}")

@app.route("/process-image", methods=["POST"])
def process_image_api():
    """处理上传的图像并返回分析结果"""
    if "image" not in request.files:
        return jsonify({"error": "No image provided"}), 400

    image_file = request.files["image"]
    if image_file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    try:
        # 生成唯一的临时文件路径
        temp_image_path = generate_temp_filepath()
        image_file.save(temp_image_path)

        # 设置检测方法（根据需要进行调整）
        set_detection_method("basic")  # 或者根据请求参数设置

        # 调用现有的图像处理函数
        main_design_choices, analyses, final_analysis = process_image(temp_image_path)

        # 清理临时文件
        cleanup_temp_file(temp_image_path)

        # 返回结果
        return jsonify(
            {
                "main_design_choices": main_design_choices,
                "analyses": analyses,
                "final_analysis": final_analysis,
            }
        )

    except Exception as e:
        # 确保发生异常时也清理临时文件
        if "temp_image_path" in locals():
            cleanup_temp_file(temp_image_path)
        return jsonify({"error": str(e)}), 500


@app.route("/process-image-url", methods=["POST"])
def process_image_url_api():
    """处理通过URL上传的图像并返回分析结果"""
    data = request.get_json()
    if "image_url" not in data:
        return jsonify({"error": "No image URL provided"}), 400

    image_url = data["image_url"]

    try:
        # 下载图像并保存到唯一的临时文件
        response = requests.get(image_url)
        response.raise_for_status()  # 检查请求是否成功

        temp_image_path = generate_temp_filepath()
        with open(temp_image_path, "wb") as f:
            f.write(response.content)

        # 设置检测方法（根据需要进行调整）
        set_detection_method("basic")  # 或者根据请求参数设置

        # 调用现有的图像处理函数
        main_design_choices, analyses, final_analysis = process_image(temp_image_path)

        # 清理临时文件
        cleanup_temp_file(temp_image_path)

        # 返回结果
        return jsonify(
            {
                "main_design_choices": main_design_choices,
                "analyses": analyses,
                "final_analysis": final_analysis,
            }
        )

    except Exception as e:
        # 确保发生异常时也清理临时文件
        if "temp_image_path" in locals():
            cleanup_temp_file(temp_image_path)
        return jsonify({"error": str(e)}), 500

class StandaloneApplication(BaseApplication):
    """Gunicorn 应用程序封装类"""

    def __init__(self, app, options=None):
        self.options = options or {}
        self.application = app
        super().__init__()

    def load_config(self):
        for key, value in self.options.items():
            if key in self.cfg.settings and value is not None:
                self.cfg.set(key.lower(), value)

    def load(self):
        return self.application

def create_pid_file(pid_file: str):
    """创建 PID 文件"""
    with open(pid_file, "w") as f:
        f.write(str(os.getpid()))


def remove_pid_file(pid_file: str):
    """删除 PID 文件"""
    try:
        if os.path.exists(pid_file):
            os.remove(pid_file)
    except Exception as e:
        print(f"删除 PID 文件失败: {str(e)}")


def daemonize():
    """将进程转换为守护进程"""
    try:
        # 第一次 fork
        pid = os.fork()
        if pid > 0:
            sys.exit(0)  # 父进程退出
    except OSError as err:
        sys.stderr.write(f"第一次 fork 失败: {err}\n")
        sys.exit(1)

    # 获取当前工作目录
    current_dir = os.getcwd()

    # 创建新的会话
    os.setsid()
    # 修改文件创建掩码
    os.umask(0)

    try:
        # 第二次 fork
        pid = os.fork()
        if pid > 0:
            sys.exit(0)  # 第二个父进程退出
    except OSError as err:
        sys.stderr.write(f"第二次 fork 失败: {err}\n")
        sys.exit(1)

    # 确保工作目录存在
    if not os.path.exists(current_dir):
        os.makedirs(current_dir)

    # 切换到工作目录
    os.chdir(current_dir)


def signal_handler(signo, frame):
    """信号处理函数"""
    if signo in (signal.SIGTERM, signal.SIGINT):
        cleanup()
        sys.exit(0)


def cleanup():
    """清理函数"""
    try:
        if os.path.exists(pid_file):
            os.remove(pid_file)
    except Exception as e:
        sys.stderr.write(f"清理 PID 文件失败: {e}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UI Screenshot to Prompt API Server")
    parser.add_argument("--daemon", action="store_true", help="在后台运行服务")
    args = parser.parse_args()

    # 获取当前目录的绝对路径
    base_dir = os.path.abspath(os.path.dirname(__file__))

    # PID 文件路径
    pid_file = os.path.join(base_dir, "api_server.pid")

    if args.daemon:
        # 如果是后台运行模式，将输出重定向到日志文件
        log_dir = os.path.join(base_dir, "logs")
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        log_file = os.path.join(log_dir, "api_server.log")
        access_log = os.path.join(log_dir, "access.log")
        error_log = os.path.join(log_dir, "error.log")

        # 将进程转为守护进程
        daemonize()

        # 重定向标准输出和错误
        sys.stdout = open(log_file, "a", buffering=1)
        sys.stderr = sys.stdout

        # 注册信号处理器
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        # 注册退出时的清理函数
        atexit.register(cleanup)

        # 创建 PID 文件
        create_pid_file(pid_file)

        print(f"服务器正在后台启动...")

    try:
        # Gunicorn 配置
        options = {
            "bind": "0.0.0.0:5003",
            "workers": multiprocessing.cpu_count() * 2 + 1,
            "worker_class": "sync",
            "timeout": 120,
            "accesslog": access_log if args.daemon else "-",
            "errorlog": error_log if args.daemon else "-",
            "loglevel": "info",
            "daemon": True if args.daemon else False,
            "capture_output": True,
            "pidfile": pid_file if args.daemon else None,
        }

        if args.daemon:
            print(f"""
=================================================
服务器已成功启动在后台运行！

- PID 文件：{pid_file}
- 日志目录：{log_dir}/
  - 主日志：api_server.log
  - 访问日志：access.log
  - 错误日志：error.log
- 服务地址：http://0.0.0.0:5003

要检查服务状态：
    ps aux | grep api.py
    
要查看日志：
    tail -f {log_file}
    tail -f {access_log}
    tail -f {error_log}
    
要停止服务：
    kill $(cat {pid_file})
=================================================
""")

        StandaloneApplication(app, options).run()
    except Exception as e:
        print(f"启动服务器时发生错误: {e}")
        if args.daemon:
            cleanup()
        sys.exit(1)
