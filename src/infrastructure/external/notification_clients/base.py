"""
通知客户端基类
定义通知客户端的统一接口
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List

from src.utils import convert_goofish_link

APP_NAME = "AI Eye Hunter"


@dataclass(frozen=True)
class NotificationMessage:
    title: str
    price: str
    reason: str
    desktop_link: str
    mobile_link: str | None
    notification_title: str
    content: str
    image_url: str | None
    task_name: str = ""
    spec: str = ""
    seller: str = ""
    risk_tags: List[str] = field(default_factory=list)


class NotificationClient(ABC):
    """通知客户端抽象基类"""

    channel_key = "unknown"
    display_name = "未知渠道"

    def __init__(self, enabled: bool = False, pcurl_to_mobile: bool = True):
        self._enabled = enabled
        self._pcurl_to_mobile = pcurl_to_mobile

    def is_enabled(self) -> bool:
        """检查客户端是否启用"""
        return self._enabled

    @abstractmethod
    async def send(self, product_data: Dict, reason: str) -> bool:
        """
        发送通知

        Args:
            product_data: 商品数据
            reason: 推荐原因

        Returns:
            是否发送成功
        """
        raise NotImplementedError

    def _build_message(self, product_data: Dict, reason: str) -> NotificationMessage:
        """格式化消息内容。兼容完整 record 与纯商品信息两种入参。"""
        record = product_data or {}
        nested_item = record.get("商品信息")
        if isinstance(nested_item, dict):
            item_data = nested_item
        else:
            item_data = record
            record = {"商品信息": record}

        title = item_data.get("商品标题", "N/A")
        price = item_data.get("当前售价", "N/A")
        desktop_link = item_data.get("商品链接", "#")
        mobile_link = None

        if self._pcurl_to_mobile and desktop_link and desktop_link != "#":
            mobile_link = convert_goofish_link(desktop_link)

        task_name = str(record.get("任务名称") or "")
        seller_info = record.get("卖家信息") or {}
        seller = str(seller_info.get("卖家昵称") or item_data.get("卖家昵称") or "")
        analysis = record.get("ai_analysis") or {}
        risk_tags = [str(t) for t in (analysis.get("risk_tags") or [])]

        spec_parts: list[str] = []
        for key in ("分类", "基因"):
            value = item_data.get(key)
            if value:
                spec_parts.append(str(value))
        sex = item_data.get("性别")
        if sex:
            spec_parts.append(f"公母:{sex}")
        size = item_data.get("克重") or item_data.get("体长") or item_data.get("足展")
        if size:
            spec_parts.append(str(size))
        spec = " · ".join(spec_parts)

        content_lines = [f"价格: {price}"]
        if spec:
            content_lines.append(f"规格: {spec}")
        if seller:
            content_lines.append(f"卖家: {seller}")
        if risk_tags:
            content_lines.append(f"风险: {', '.join(risk_tags)}")
        content_lines.append(f"原因: {reason}")
        if mobile_link:
            content_lines.append(f"手机端链接: {mobile_link}")
            content_lines.append(f"电脑端链接: {desktop_link}")
        else:
            content_lines.append(f"链接: {desktop_link}")

        short_title = title[:30]
        suffix = "..." if len(title) > 30 else ""
        notification_title = f"【{APP_NAME}】🚨 新推荐! {short_title}{suffix}"

        main_image = item_data.get("商品主图链接")
        if not main_image:
            image_list = item_data.get("商品图片列表", [])
            if image_list:
                main_image = image_list[0]

        return NotificationMessage(
            title=title,
            price=price,
            reason=reason,
            desktop_link=desktop_link,
            mobile_link=mobile_link,
            notification_title=notification_title,
            content="\n".join(content_lines),
            image_url=main_image,
            task_name=task_name,
            spec=spec,
            seller=seller,
            risk_tags=risk_tags,
        )
