import requests
from pathlib import Path

class DeepSeekOCRClient:
    def __init__(self, base_url: str = "http://localhost:5000"):
        """
        初始化 OCR 客户端
        
        :param base_url: OCR 服务的根地址，例如 "http://localhost:5000"
        """
        self.base_url = base_url.rstrip('/')
        self.ocr_endpoint = f"{self.base_url}/ocr"

    def ocr_image(self, image_path: str) -> dict:
        """
        上传本地图片并获取 OCR 结果（Markdown 格式）
        
        :param image_path: 本地图片路径（支持 PNG/JPG）
        :return: 包含 'request_id', 'markdown' 和 'images' 的字典
        :raises: requests.HTTPError, FileNotFoundError 等
        """
        image_path = Path(image_path)
        if not image_path.is_file():
            raise FileNotFoundError(f"Image file not found: {image_path}")

        # 确保是图片格式
        if image_path.suffix.lower() not in {'.png', '.jpg', '.jpeg'}:
            raise ValueError("Only PNG/JPG images are supported")

        with open(image_path, 'rb') as f:
            files = {'file': (image_path.name, f, 'image/png')}
            response = requests.post(self.ocr_endpoint, files=files)

        # 抛出 HTTP 错误
        response.raise_for_status()

        result = response.json()
        
        # 处理图片数据，将bytes转换为base64编码以便传输
        if 'images' in result and result['images']:
            import base64
            processed_images = []
            for img_data in result['images']:
                if isinstance(img_data, dict) and 'data' in img_data:
                    # 将bytes转换为base64字符串
                    img_data_copy = img_data.copy()
                    img_data_copy['data'] = base64.b64encode(img_data['data']).decode('utf-8')
                    processed_images.append(img_data_copy)
                else:
                    processed_images.append(img_data)
            result['images'] = processed_images
        
        return result


# ----------------------------
# 使用示例
# ----------------------------
if __name__ == "__main__":
    client = DeepSeekOCRClient("http://192.168.31.65:5000")
    try:
        result = client.ocr_image("test.png")
        print("Request ID:", result["request_id"])
        print("Markdown Result:\n")
        print(result["markdown"])
    except Exception as e:
        print("Error:", e)