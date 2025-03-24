import os
import asyncio
import yaml
from typing import List
from pkg.plugin.context import register, handler, BasePlugin, APIHost, EventContext
from pkg.plugin.events import PersonNormalMessageReceived, GroupNormalMessageReceived
from pkg.platform.types.message import MessageChain, Plain, Image
from plugins.pica_plugin.get_image import get_pica_images, search_comics, get_comic_episodes
from plugins.pica_plugin.forward_message import ForwardMessageBuilder, build_message_chain, build_forward_message

config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "yaml", "config.yaml")
with open(config_path, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

MAX_SEARCH_RESULTS = config.get("max_search_results", 10)


@register(name="看漫画",description="漫画搜索和下载查看插件",version="0.1",author="小馄饨")

class PicaPlugin(BasePlugin):
    download_tasks: List[asyncio.Task] = []
    
    def __init__(self, host: APIHost):
        super().__init__(host)
        self.forward_message = ForwardMessageBuilder(host="127.0.0.1", port=3000)
    
    async def initialize(self):
        cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
        os.makedirs(cache_dir, exist_ok=True)
    
    @handler(PersonNormalMessageReceived)
    async def person_message_received(self, ctx: EventContext):
        msg = ctx.event.text_message.strip()
        
        if msg.startswith("搜漫画"):
            ctx.prevent_default()
            await self._search_comics(ctx, msg)
        
        elif msg.startswith("看漫画"):
            ctx.prevent_default()
            await self._download_comic(ctx, msg)
        
        elif msg == "漫画帮助":
            ctx.prevent_default()
            await self._show_help(ctx)
    
    @handler(GroupNormalMessageReceived)
    async def group_message_received(self, ctx: EventContext):
        msg = ctx.event.text_message.strip()
        
        if msg.startswith("搜漫画"):
            ctx.prevent_default()
            await self._search_comics(ctx, msg)
        
        elif msg.startswith("看漫画"):
            ctx.prevent_default()
            await self._download_comic(ctx, msg)
        
        elif msg == "漫画帮助":
            ctx.prevent_default()
            await self._show_help(ctx)
    
    async def _search_comics(self, ctx: EventContext, msg: str):
        parts = msg.split()
        if len(parts) < 2:
            await ctx.reply(MessageChain([Plain("请提供搜索关键词，例如：搜漫画 关键词 [页码]")]))
            return
        
        keyword = parts[1].strip()
        if not keyword:
            await ctx.reply(MessageChain([Plain("请提供搜索关键词，例如：搜漫画 关键词 [页码]")]))
            return
        
        page = 1
        if len(parts) >= 3:
            try:
                page = int(parts[2].strip())
                if page < 1:
                    page = 1
            except ValueError:
                pass
        
        await ctx.reply(MessageChain([Plain(f"正在搜索：{keyword}，第{page}页，请稍候...")]))
        
        try:
            response = await search_comics(keyword, page)
            comics = response.get("data", {}).get("comics", {}).get("docs", [])
            
            if not comics:
                await ctx.reply(MessageChain([Plain(f"未找到关键词 '{keyword}' 相关的漫画(第{page}页)")]))
                return
            
            result_message = [f"搜索结果(第{page}页)："]
            for i, comic in enumerate(comics[:MAX_SEARCH_RESULTS]):
                title = comic.get("title", "未知标题")
                id = comic.get("_id", "")
                description = comic.get("description", "无简介")
                
                result_message.append(f"{i+1}. {title}")
                result_message.append(f"   ID: {id}")
                result_message.append(f"   简介: {description[:100]}{'...' if len(description) > 100 else ''}")
                result_message.append("")
            
            result_message.append("使用方式：看漫画 漫画ID")
            result_message.append("搜索翻页：搜漫画 关键词 页码")
            
            await ctx.reply(MessageChain([Plain("\n".join(result_message))]))
            
        except Exception as e:
            self.ap.logger.error(f"搜索漫画失败: {str(e)}")
            await ctx.reply(MessageChain([Plain(f"搜索失败: {str(e)}")]))
    
    async def _download_comic(self, ctx: EventContext, msg: str):
        """下载漫画"""
        parts = msg.split()
        if len(parts) < 2:
            await ctx.reply(MessageChain([Plain("请提供漫画ID，例如：看漫画 漫画ID")]))
            return
        
        comic_id = parts[1]
        
        await ctx.reply(MessageChain([Plain(f"正在获取漫画信息，请稍候...")]))
        
        download_task = asyncio.create_task(
            self._process_download_all(ctx, comic_id)
        )
        self.download_tasks.append(download_task)
        
        self._clean_finished_tasks()
    
    async def _process_download_all(self, ctx: EventContext, comic_id: str):
        try:
            episode_info = await get_comic_episodes(comic_id)
            episodes = episode_info.get("data", {}).get("eps", {}).get("docs", [])
            
            if not episodes:
                await ctx.reply(MessageChain([Plain("未找到章节信息")]))
                return
            
            total_eps = len(episodes)
            await ctx.reply(MessageChain([Plain(f"漫画共有 {total_eps} 章，开始下载全部章节，请耐心等待...")]))
            
            for ep in range(1, total_eps + 1):
                try:
                    comic_info, images, title = await get_pica_images(comic_id, ep)
                    
                    await ctx.reply(MessageChain([
                        Plain(f"第{ep}章下载完成: '{title}'，共{len(images)}页，正在发送...")
                    ]))
                    
                    if isinstance(ctx.event, GroupNormalMessageReceived):
                        target_type = "group"
                        target_id = str(ctx.event.launcher_id)
                    else:
                        target_type = "person"
                        target_id = str(ctx.event.sender_id)
                    
                    try:
                        if hasattr(self, "forward_message"):
                            result = await self.forward_message.send(target_type, target_id, comic_info, images)
                            
                            if not result:
                                self.ap.logger.warning(f"第{ep}章API合并转发发送失败，尝试使用内置合并转发")
                                forward_chain = await build_forward_message(comic_info, images)
                                await ctx.reply(forward_chain)
                        else:
                            forward_chain = await build_forward_message(comic_info, images)
                            await ctx.reply(forward_chain)
                            
                    except Exception as e:
                        self.ap.logger.error(f"第{ep}章发送合并转发消息失败: {str(e)}")
                        message_chain = await build_message_chain(comic_info, images)
                        await ctx.reply(message_chain)
                
                except Exception as e:
                    self.ap.logger.error(f"下载第{ep}章失败: {str(e)}")
                    await ctx.reply(MessageChain([Plain(f"下载第{ep}章失败: {str(e)}")]))
            
            await ctx.reply(MessageChain([Plain(f"全部 {total_eps} 章节处理完成")]))
                
        except Exception as e:
            self.ap.logger.error(f"获取漫画章节信息失败: {str(e)}")
            await ctx.reply(MessageChain([Plain(f"获取漫画章节信息失败: {str(e)}")]))
    
    def _clean_finished_tasks(self):
        self.download_tasks = [task for task in self.download_tasks if not task.done()]
    
    async def _show_help(self, ctx: EventContext):
        """显示帮助信息"""
        help_text = [
            "漫画搜索下载插件使用帮助",
            "",
            "【搜索漫画】",
            "命令：搜漫画 关键词 [页码]",
            "说明：搜索漫画，返回搜索结果，可指定页码",
            "",
            "【下载漫画】",
            "命令：看漫画 漫画ID",
            "说明：下载指定ID的漫画全部章节",
            "",
            "【帮助信息】",
            "命令：漫画帮助",
            "说明：显示插件帮助信息"
        ]
        
        await ctx.reply(MessageChain([Plain("\n".join(help_text))]))
    
    def __del__(self):
        for task in self.download_tasks:
            if not task.done():
                task.cancel()
        self.download_tasks.clear() 
