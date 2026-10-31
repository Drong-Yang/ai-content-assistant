"""Volcano Ark images API. Failures retain their topic and are never replaced by unrelated images."""
import asyncio
import base64
import os
import uuid
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[2]


class ImageService:
    def __init__(self):
        self.api_key = os.getenv('IMAGE_API_KEY', '') or os.getenv('LLM_API_KEY', '')
        self.base_url = os.getenv('IMAGE_BASE_URL', 'https://ark.cn-beijing.volces.com/api/v3').rstrip('/')
        self.model = os.getenv('IMAGE_MODEL', '')
        self.mock = os.getenv('MOCK_MODE', 'false').lower() == 'true'
        self.image_dir = ROOT / 'static/images/generated'

    async def generate_single_image(self, prompt: str, optimize_for_xhs: bool = True):
        self.image_dir.mkdir(parents=True, exist_ok=True)
        if self.mock:
            name = 'mock_' + uuid.uuid4().hex + '.svg'
            (self.image_dir / name).write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="800">'
                '<rect width="600" height="800" fill="#eef2ff"/>'
                '<text x="40" y="400" font-size="28">MOCK IMAGE - NOT AI GENERATED</text></svg>',
                encoding='utf-8')
            return '/static/images/generated/' + name
        if not self.api_key or not self.model:
            raise ValueError('请配置 IMAGE_API_KEY（或 LLM_API_KEY）及 IMAGE_MODEL')
        payload = {'model': self.model, 'prompt': (
            '为教育技术文章制作清晰的小红书知识配图，竖版3:4，内容紧扣以下主题：' + prompt
            if optimize_for_xhs else prompt),
            'size': os.getenv('IMAGE_SIZE', '1728x2304'), 'response_format': 'b64_json',
            'stream': False, 'watermark': True}
        async with httpx.AsyncClient(timeout=httpx.Timeout(180, connect=15), trust_env=False) as client:
            for attempt in range(3):
                try:
                    response = await client.post(self.base_url + '/images/generations',
                        headers={'Authorization': 'Bearer ' + self.api_key}, json=payload)
                    response.raise_for_status()
                    result = response.json()
                    item = result.get('data', [{}])[0]
                    if item.get('error') or not item.get('b64_json'):
                        raise ValueError('图片接口未返回 b64_json，请核对模型支持的返回格式')
                    data = base64.b64decode(item['b64_json'], validate=True)
                    if data.startswith(b'\x89PNG\r\n\x1a\n'):
                        suffix = '.png'
                    elif data.startswith(b'\xff\xd8\xff'):
                        suffix = '.jpg'
                    elif data[:4] == b'RIFF' and data[8:12] == b'WEBP':
                        suffix = '.webp'
                    else:
                        raise ValueError('图片接口返回了无法识别的图片格式')
                    name = 'xhs_' + uuid.uuid4().hex + suffix
                    (self.image_dir / name).write_bytes(data)
                    return '/static/images/generated/' + name
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code not in (429, 500, 502, 503, 504) or attempt == 2:
                        raise RuntimeError(f'图片接口 HTTP {exc.response.status_code}，请检查模型权限和配额') from exc
                except httpx.TransportError:
                    if attempt == 2:
                        raise RuntimeError('图片接口网络失败或超时')
                await asyncio.sleep(2 ** attempt)

    async def generate_images(self, visual_points: list[str], optimize_for_xhs: bool = True):
        semaphore = asyncio.Semaphore(2)
        async def generate(point):
            async with semaphore:
                return await self.generate_single_image(point, optimize_for_xhs)
        results = await asyncio.gather(*(generate(point) for point in visual_points[:5]), return_exceptions=True)
        urls = [item for item in results if isinstance(item, str)]
        if results and not urls:
            raise RuntimeError('所有配图失败: ' + str(results[0]))
        return urls


image_service = ImageService()
