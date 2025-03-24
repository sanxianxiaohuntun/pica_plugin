import os
import re
import yaml
from typing import List, Dict, Any, Tuple
from .pica_client import PicaClient

config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "yaml", "config.yaml")
with open(config_path, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

PICA_ACCOUNT = config.get("account", "")
PICA_PASSWORD = config.get("password", "")
PROXY = config.get("proxy")
MAX_PREVIEW_PAGES = config.get("max_preview_pages", 10)

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

FILENAME_PATTERN = r"[\\\/\:\*\?\"\<\>\|]"

client = PicaClient(proxy=PROXY)

async def login():
    if not PICA_ACCOUNT or not PICA_PASSWORD:
        raise Exception("请在plugins\\pica_plugin\\yaml\\config.yaml配置账号密码")
    
    if not client.is_login and PICA_ACCOUNT and PICA_PASSWORD:
        try:
            await client.login(PICA_ACCOUNT, PICA_PASSWORD)
            return True
        except Exception as e:
            raise Exception(f"登录哔咔账号失败: {str(e)}")
    return client.is_login

async def search_comics(keyword: str, page: int = 1) -> Dict[str, Any]:
    if not await login():
        raise Exception("哔咔账号未登录，请检查配置")
    
    response = await client.search(keyword, page=page)
    return response

async def get_comic_info(comic_id: str) -> Dict[str, Any]:
    if not await login():
        raise Exception("哔咔账号未登录，请检查配置")
    
    comic_info = await client.comic_info(comic_id)
    return comic_info

async def get_comic_episodes(comic_id: str) -> Dict[str, Any]:
    if not await login():
        raise Exception("哔咔账号未登录，请检查配置")
    
    episode_info = await client.episodes(comic_id)
    return episode_info

async def download_comic_images(comic_id: str, ep: int, safe_title: str) -> Tuple[List[str], int]:
    if not await login():
        raise Exception("哔咔账号未登录，请检查配置")
    
    comic_dir = os.path.join(CACHE_DIR, safe_title)
    os.makedirs(comic_dir, exist_ok=True)
    
    picture_info = await client.picture(comic_id, ep)
    pages = picture_info.get("data", {}).get("pages", {}).get("docs", [])
    
    if not pages:
        raise Exception("未找到图片信息")
    
    total_pages = len(pages)
    downloaded_images = []
    
    for i, page in enumerate(pages):
        media = page.get("media", {})
        image_url = media.get("orig") or media.get("fileServer") + "/static/" + media.get("path")
        
        image_path = os.path.join(comic_dir, f"{safe_title}-{i+1}.jpg")
        
        if os.path.exists(image_path):
            downloaded_images.append(image_path)
            continue
        
        success = await client.download_image(image_url, image_path)
        if success:
            downloaded_images.append(image_path)
    
    if not downloaded_images:
        raise Exception("未能下载任何图片，请检查网络连接或考虑配置代理服务器")
    
    return downloaded_images, total_pages

async def get_pica_images(comic_id: str, ep: int = 1) -> Tuple[Dict[str, Any], List[str], str]:
    if not await login():
        raise Exception("哔咔账号未登录，请检查配置")
    
    comic_info = await get_comic_info(comic_id)
    comic_data = comic_info.get("data", {}).get("comic", {})
    title = comic_data.get("title", "未知标题")
    
    safe_title = re.sub(FILENAME_PATTERN, "_", title)
    
    episode_info = await get_comic_episodes(comic_id)
    episodes = episode_info.get("data", {}).get("eps", {}).get("docs", [])
    
    if not episodes:
        raise Exception("未找到章节信息")
    
    if ep < 1 or ep > len(episodes):
        raise Exception(f"章节号无效，漫画 '{title}' 共有 {len(episodes)} 章")
    
    downloaded_images, total_pages = await download_comic_images(comic_id, ep, safe_title)
    
    if not downloaded_images:
        raise Exception("未能下载任何图片，请检查网络连接或考虑配置代理服务器")
    
    return comic_info, downloaded_images, safe_title
