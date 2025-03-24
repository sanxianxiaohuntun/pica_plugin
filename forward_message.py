import os
import json
import aiohttp
import yaml
from typing import List, Dict, Any
from PIL import Image as PILImage
from pkg.platform.types.message import MessageChain, Plain, Image, ForwardMessageNode, ForwardMessageDiaplay, Forward

config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "yaml", "config.yaml")
with open(config_path, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

FORWARD_CONFIG = config.get("forward", {})
SENDER_NAME = FORWARD_CONFIG.get("sender_name", "漫画")
SENDER_ID = FORWARD_CONFIG.get("sender_id", "3870128501")
MAX_PREVIEW_PAGES = config.get("max_preview_pages", 10)
MAX_IMAGE_HEIGHT = config.get("max_image_height", 20000)


async def merge_images(image_paths: List[str], max_height: int = MAX_IMAGE_HEIGHT) -> List[str]:

    if not image_paths:
        return []

    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pica_plugin", "cache", "merged")
    os.makedirs(output_dir, exist_ok=True)

    merged_image_paths = []
    
    try:
        image_objects = []
        for img_path in image_paths:
            if img_path.startswith(('http://', 'https://')):
                continue
            
            try:
                img = PILImage.open(img_path)
                image_objects.append((img, img_path))
            except Exception as e:
                print(f"打开图片失败: {img_path}, 错误: {e}")
                continue
        
        if not image_objects:
            return []

        current_batch = []
        current_height = 0
        batch_number = 1
        
        for img, img_path in image_objects:
            if not current_batch or current_height + img.height <= max_height:
                current_batch.append((img, img_path))
                current_height += img.height
            else:
                merged_path = await _merge_batch(current_batch, output_dir, batch_number)
                if merged_path:
                    merged_image_paths.append(merged_path)
                
                current_batch = [(img, img_path)]
                current_height = img.height
                batch_number += 1
        
        if current_batch:
            merged_path = await _merge_batch(current_batch, output_dir, batch_number)
            if merged_path:
                merged_image_paths.append(merged_path)
        
        if not merged_image_paths and image_paths:
            return [image_paths[0]]
            
        return merged_image_paths
        
    except Exception as e:
        print(f"合并图片过程中出错: {e}")
        return [image_paths[0]] if image_paths else []


async def _merge_batch(batch: List[tuple], output_dir: str, batch_number: int) -> str:

    if not batch:
        return None
    
    _, first_path = batch[0]
    basename = os.path.basename(first_path)
    output_path = os.path.join(output_dir, f"merged_{batch_number}_{basename}")
    
    try:
        images = [img for img, _ in batch]
        width = max(img.width for img in images)
        total_height = sum(img.height for img in images)
        
        merged_image = PILImage.new("RGB", (width, total_height))
        
        y_offset = 0
        for img, _ in batch:
            x_offset = (width - img.width) // 2
            merged_image.paste(img, (x_offset, y_offset))
            y_offset += img.height
        
        merged_image.save(output_path)
        return output_path
    
    except Exception as e:
        print(f"合并批次图片失败: {e}")
        _, path = batch[0]
        return path


class ForwardMessageBuilder:
    
    def __init__(self, host: str = "127.0.0.1", port: int = 3000):
        self.url = f"http://{host}:{port}"
    
    async def send(self, target_type: str, target_id: str, comic_info: Dict[str, Any], images: List[str]):

        comic_data = comic_info.get("data", {}).get("comic", {})
        title = comic_data.get("title", "未知标题")
        comic_id = comic_data.get("_id", "")
        description = comic_data.get("description", "无简介")
        
        messages = []
        
        messages.append({
            "type": "node",
            "data": {
                "user_id": SENDER_ID,
                "nickname": SENDER_NAME,
                "content": [
                    {
                        "type": "text",
                        "data": {
                            "text": f"标题：{title}\nID：{comic_id}\n简介：{description}\n"
                        }
                    }
                ]
            }
        })
        
        merged_image_paths = await merge_images(images)
        
        if merged_image_paths:
            for i, merged_path in enumerate(merged_image_paths):
                image_file = self.get_media_path(merged_path)
                
                messages.append({
                    "type": "node",
                    "data": {
                        "user_id": SENDER_ID,
                        "nickname": SENDER_NAME,
                        "content": [
                            {
                                "type": "text",
                                "data": {
                                    "text": f"图 {i+1}/{len(merged_image_paths)}"
                                }
                            },
                            {
                                "type": "image",
                                "data": {
                                    "file": image_file,
                                }
                            }
                        ]
                    }
                })
        else:
            for i, img_path in enumerate(images[:MAX_PREVIEW_PAGES]):
                if img_path.startswith(('http://', 'https://')):
                    image_file = img_path
                else:
                    image_file = self.get_media_path(img_path)
                
                messages.append({
                    "type": "node",
                    "data": {
                        "user_id": SENDER_ID,
                        "nickname": SENDER_NAME,
                        "content": [
                            {
                                "type": "text",
                                "data": {
                                    "text": f"第{i+1}页"
                                }
                            },
                            {
                                "type": "image",
                                "data": {
                                    "file": image_file,
                                }
                            }
                        ]
                    }
                })
        
        message_data = {}
        
        if target_type == "group":
            message_data = {
                "group_id": target_id,
                "user_id": SENDER_ID,
                "messages": messages,
                "news": [
                    {
                        "text": f"漫画 - {title}"
                    }
                ],
                "prompt": "漫画预览",
                "summary": f"{'合并图片预览' if merged_image_paths else f'共{len(images)}张预览图'}",
                "source": title
            }
            endpoint = "/send_forward_msg"
        else:
            message_data = {
                "user_id": target_id,
                "messages": messages,
                "news": [
                    {
                        "text": f"漫画 - {title}"
                    }
                ],
                "prompt": "漫画预览",
                "summary": f"{'合并图片预览' if merged_image_paths else f'共{len(images)}张预览图'}",
                "source": title
            }
            endpoint = "/send_private_forward_msg"
        
        headers = {
            'Content-Type': 'application/json'
        }
        payload = json.dumps(message_data)
        try:
            async with aiohttp.ClientSession(self.url, headers=headers) as session:
                async with session.post(endpoint, data=payload) as response:
                    return await response.json()
        except Exception as e:
            print(f"发送合并转发消息失败: {str(e)}")
            return None
    
    def get_media_path(self, media_path):
        if media_path:
            if media_path.startswith('http'):
                return media_path
            elif os.path.isfile(media_path):
                abspath = os.path.abspath(os.path.join(os.getcwd(), media_path)).replace('\\', '\\\\')
                return f"file:///{abspath}"
        return ''


async def build_forward_message(comic_info: Dict[str, Any], images: List[str]) -> MessageChain:

    comic_data = comic_info.get("data", {}).get("comic", {})
    title = comic_data.get("title", "未知标题")
    comic_id = comic_data.get("_id", "")
    description = comic_data.get("description", "无简介")
    
    nodes = []
    
    info_text = f"标题：{title}\nID：{comic_id}\n简介：{description}\n"
    info_node = ForwardMessageNode(
        sender_id=SENDER_ID,
        sender_name=SENDER_NAME,
        message_chain=MessageChain([Plain(info_text)])
    )
    nodes.append(info_node)
    
    try:
        merged_image_paths = await merge_images(images)
    except Exception as e:
        print(f"合并图片失败: {e}")
        merged_image_paths = None
    
    if merged_image_paths:
        for i, merged_path in enumerate(merged_image_paths):
            components = [Plain(f"图 {i+1}/{len(merged_image_paths)}")]
            components.append(Image(path=os.path.abspath(merged_path)))
            
            node = ForwardMessageNode(
                sender_id=SENDER_ID,
                sender_name=SENDER_NAME,
                message_chain=MessageChain(components)
            )
            nodes.append(node)
    else:
        for i, img_path in enumerate(images[:MAX_PREVIEW_PAGES]):
            components = [Plain(f"第{i+1}页")]
            
            if img_path.startswith(('http://', 'https://')):
                components.append(Image(url=img_path))
            else:
                components.append(Image(path=os.path.abspath(img_path)))
            
            node = ForwardMessageNode(
                sender_id=SENDER_ID,
                sender_name=SENDER_NAME,
                message_chain=MessageChain(components)
            )
            nodes.append(node)
    
    display = ForwardMessageDiaplay(
        title=f"漫画 - {title}",
        brief=f"[漫画预览] {title}",
        source="漫画",
        summary=f"{'合并图片预览' if merged_image_paths else f'共{len(images)}张预览图'}"
    )
    
    forward = Forward(
        display=display,
        node_list=nodes
    )
    
    return MessageChain([forward])


async def build_message_chain(comic_info: Dict[str, Any], images: List[str]) -> MessageChain:

    comic_data = comic_info.get("data", {}).get("comic", {})
    title = comic_data.get("title", "未知标题")
    comic_id = comic_data.get("_id", "")
    description = comic_data.get("description", "无简介")
    
    text = f"标题：{title}\nID：{comic_id}\n简介：{description[:100]}\n{'...' if len(description) > 100 else ''}"
    
    components = [Plain(text)]

    if images:
        try:
            merged_image_paths = await merge_images(images)
        except Exception as e:
            print(f"在build_message_chain中合并图片失败: {e}")
            merged_image_paths = None
            
        if merged_image_paths:
            img_path = merged_image_paths[0]
            components.append(Plain(f"\n[注意] 成功合并{len(merged_image_paths)}组图片，仅预览第一组"))
            
            if img_path.startswith(('http://', 'https://')):
                components.append(Image(url=img_path))
            else:
                components.append(Image(path=os.path.abspath(img_path)))
        else:
            img_path = images[0]
            components.append(Plain("\n[注意] 图片未合并，仅预览第一张"))
            
            if img_path.startswith(('http://', 'https://')):
                components.append(Image(url=img_path))
            else:
                components.append(Image(path=os.path.abspath(img_path)))
    
    return MessageChain(components) 