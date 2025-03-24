from time import time
import aiohttp
import hmac
import hashlib
from typing import Optional, Dict, List, Any
import os
from asyncio.exceptions import TimeoutError

try:
    import ujson as json
except:
    import json

nonce = "b1ab87b4800d4d4590a11701b8551afa"
api_key = "C69BAF41DA5ABD1FFEDC6D2FEA56B"
secret_key = r"~d}$Q7$eIni=V)9\RK/P.RM4;9[7|@/CA}b~OW!3?EV`:<>M7pddUBL5n|0/*Cn"
base = "https://picaapi.picacomic.com"

class PicaClient:
    Order_Default = "ua"
    Order_Latest = "dd"
    Order_Oldest = "da"
    Order_Loved = "ld"
    Order_Point = "vd"

    def __init__(self, proxy: Optional[str] = None) -> None:
        self.proxy = proxy
        self.headers = {
            "api-key":           api_key,
            "accept":            "application/vnd.picacomic.com.v1+json",
            "app-channel":       "2",
            "nonce":             nonce,
            "app-version":       "2.2.1.2.3.3",
            "app-uuid":          "defaultUuid",
            "app-platform":      "android",
            "app-build-version": "44",
            "Content-Type":      "application/json; charset=UTF-8",
            "User-Agent":        "okhttp/3.8.1",
            "image-quality":     "original",
            "time":              int(time()),
        }
        self.is_login = False

    async def http_request(self, method: str, url: str, json_data: str = "") -> Dict[str, Any]:
        header = self.headers.copy()
        ts = str(int(time()))
        raw = url.replace("https://picaapi.picacomic.com/", "") + str(ts) + nonce + method + api_key
        raw = raw.lower()
        
        hc = hmac.new(secret_key.encode(), digestmod=hashlib.sha256)
        hc.update(raw.encode())
        header["signature"] = hc.hexdigest()
        header["time"] = ts
        
        try:
            async with aiohttp.ClientSession() as session:
                if method == "GET":
                    rs = await session.get(
                        url=url, 
                        proxy=self.proxy, 
                        headers=header, 
                        ssl=False,
                        timeout=30
                    )
                elif method == "POST":
                    rs = await session.post(
                        url=url, 
                        proxy=self.proxy, 
                        headers=header, 
                        data=json_data, 
                        ssl=False,
                        timeout=30
                    )
                
                response = await rs.json()
                return response
        except TimeoutError:
            raise Exception("请求超时，请检查网络和代理设置")
        except Exception as e:
            raise Exception(f"请求失败: {str(e)}")

    async def login(self, email: str, password: str) -> bool:
        if not email or not password:
            raise Exception("请在plugins\\pica_plugin\\yaml\\config.yaml配置账号密码")
            
        api = "/auth/sign-in"
        url = base + api
        send = {"email": str(email), "password": str(password)}
        
        try:
            response = await self.http_request(method="POST", url=url, json_data=json.dumps(send))
            token = response["data"]["token"]
            self.headers["authorization"] = token
            self.is_login = True
            return True
        except Exception as e:
            self.is_login = False
            raise Exception(f"登录失败: {str(e)}")

    async def search(self, keyword: str, categories: List[str] = [], sort: str = Order_Default, page: int = 1) -> Dict[str, Any]:
        jso = {
            "categories": categories,
            "keyword": keyword,
            "sort": sort
        }
        url = f"{base}/comics/advanced-search?page={page}"
        response = await self.http_request(method="POST", url=url, json_data=json.dumps(jso))
        return response

    async def comic_info(self, book_id: str) -> Dict[str, Any]:
        url = f"{base}/comics/{book_id}"
        response = await self.http_request(method="GET", url=url)
        return response

    async def episodes(self, book_id: str, page: int = 1) -> Dict[str, Any]:
        url = f"{base}/comics/{book_id}/eps?page={page}"
        response = await self.http_request(method="GET", url=url)
        return response

    async def picture(self, book_id: str, ep_id: int = 1, page: int = 1) -> Dict[str, Any]:
        url = f"{base}/comics/{book_id}/order/{ep_id}/pages?page={page}"
        response = await self.http_request(method="GET", url=url)
        return response

    async def download_image(self, url: str, save_path: str) -> bool:
        if not self.proxy:
            return False
            
        try:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, proxy=self.proxy, ssl=False, timeout=60) as response:
                    if response.status == 200:
                        data = await response.read()
                        with open(save_path, "wb") as f:
                            f.write(data)
                        return True
                    else:
                        return False
        except Exception as e:
            return False