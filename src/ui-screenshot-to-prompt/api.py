import requests  # 新增导入
from flask import Flask, request, jsonify
from PIL import Image
import os
import uuid
import multiprocessing
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

if __name__ == "__main__":
    # Gunicorn 配置
    options = {
        "bind": "0.0.0.0:5003",
        "workers": multiprocessing.cpu_count() * 2 + 1,  # 建议的工作进程数
        "worker_class": "sync",  # 使用同步工作进程
        "timeout": 120,  # 请求超时时间
        "accesslog": "-",  # 访问日志输出到标准输出
        "errorlog": "-",  # 错误日志输出到标准输出
        "loglevel": "info",
    }

    StandaloneApplication(app, options).run()
