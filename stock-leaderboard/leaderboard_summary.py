#!/usr/bin/env uv run
# -*- coding: utf-8 -*-
# /// script
# dependencies = [
#   "requests",
#   "pyyaml",
#   "pillow",
# ]
# ///
"""
游资龙虎榜汇总脚本（简化版）
按游资分组，每只股票只显示净买卖金额，类似于交易日报格式
默认生成 JSON/YAML/图片 三种格式输出，使用 --no-image 可关闭图片生成
"""

import requests
import json
import yaml
import argparse
import os
from datetime import datetime
from typing import List, Dict, Any
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

# 检查图片生成支持
try:
    from PIL import Image, ImageDraw, ImageFont
    IMAGE_SUPPORT = True
except ImportError:
    IMAGE_SUPPORT = False
    print("⚠️  警告: 未安装 Pillow，无法生成图片。运行 'uv run' 会自动安装。")


class QuotedString(str):
    """用于强制 YAML 输出时加双引号的字符串类型"""
    pass


def quoted_string_representer(dumper, data):
    """自定义 YAML 表示器，强制使用双引号"""
    return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='"')


def load_seat_mapping() -> Dict[str, str]:
    """从 JSON 文件加载游资席位映射表"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mapping_file = os.path.join(script_dir, 'seat_mapping.json')
    
    try:
        with open(mapping_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"⚠️  警告: 未找到映射文件 {mapping_file}，使用空映射表")
        return {}
    except json.JSONDecodeError as e:
        print(f"⚠️  警告: 映射文件格式错误 - {e}")
        return {}


# 从 JSON 文件加载游资席位映射表
SEAT_MAPPING = load_seat_mapping()


def get_seat_name(dept_name: str) -> str:
    """根据营业部名称获取游资名称"""
    if not dept_name:
        return '未知席位'
    
    if dept_name in SEAT_MAPPING:
        return SEAT_MAPPING[dept_name]
    
    for key, value in SEAT_MAPPING.items():
        if key in dept_name or dept_name in key:
            return value
    
    return dept_name


def format_amount(amount: float) -> str:
    """格式化金额，保持更高精度，只在最终展示时进行格式化"""
    if abs(amount) >= 10000:
        # 使用 Decimal 提高精度
        value = Decimal(str(amount)) / Decimal('10000')
        # 保留4位小数，去除尾部的0
        formatted = f"{value:.4f}".rstrip('0').rstrip('.')
        return f"{formatted}亿"
    # 对于万级别，也使用 Decimal 保证精度
    value = Decimal(str(amount))
    # 保留2位小数，去除尾部的0
    formatted = f"{value:.2f}".rstrip('0').rstrip('.')
    return f"{formatted}万"


def get_display_width(text: str) -> int:
    """
    计算字符串的显示宽度（中文字符算2个宽度，英文算1个）
    """
    width = 0
    for char in text:
        # 判断是否为中文字符（基本汉字范围）
        if '\u4e00' <= char <= '\u9fff':
            width += 2
        else:
            width += 1
    return width


def pad_text(text: str, target_width: int) -> str:
    """
    根据显示宽度补齐字符串
    """
    current_width = get_display_width(text)
    padding = target_width - current_width
    return text + ' ' * max(0, padding)


def colorize_change_rate(change_rate_str: str) -> str:
    """
    根据涨跌给涨跌幅添加颜色
    红色代表涨，绿色代表跌
    """
    # 提取数值
    change_rate = float(change_rate_str.rstrip('%'))
    
    if change_rate > 0:
        # 红色（涨）
        return f"\033[91m{change_rate_str}\033[0m"
    elif change_rate < 0:
        # 绿色（跌）
        return f"\033[92m{change_rate_str}\033[0m"
    else:
        # 平盘（不着色）
        return change_rate_str


def get_dragon_tiger_list(trade_date: str) -> List[Dict[str, Any]]:
    """获取龙虎榜列表"""
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    params = {
        'reportName': 'RPT_DAILYBILLBOARD_DETAILS',
        'columns': 'SECURITY_CODE,SECURITY_NAME_ABBR,TRADE_DATE,EXPLAIN,CLOSE_PRICE,CHANGE_RATE,BILLBOARD_NET_AMT,BILLBOARD_BUY_AMT,BILLBOARD_SELL_AMT,ACCUM_AMOUNT',
        'filter': f"(TRADE_DATE='{trade_date}')",
        'pageNumber': 1,
        'pageSize': 500,
        'sortTypes': -1,
        'sortColumns': 'CHANGE_RATE',
        'source': 'WEB',
        'client': 'WEB'
    }
    
    response = requests.get(url, params=params)
    data = response.json()
    
    if data.get('success') and data.get('result'):
        return data['result'].get('data', [])
    return []


def get_seat_details(trade_date: str, security_code: str, report_name: str) -> List[Dict[str, Any]]:
    """获取席位明细"""
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    params = {
        'reportName': report_name,
        'columns': 'ALL',
        'filter': f'(TRADE_DATE=\'{trade_date}\')(SECURITY_CODE="{security_code}")',
        'pageNumber': 1,
        'pageSize': 50,
        'sortTypes': -1,
        'sortColumns': 'BUY' if 'BUY' in report_name else 'SELL',
        'source': 'WEB',
        'client': 'WEB'
    }
    
    response = requests.get(url, params=params)
    data = response.json()
    
    if data.get('success') and data.get('result'):
        return data['result'].get('data', [])
    return []


class SummaryImageGenerator:
    """龙虎榜汇总图片生成器"""
    
    # 配色方案（现代大气风格）
    COLOR_BG = '#FFFFFF'  # 背景色
    COLOR_TITLE_BG = '#1a1a2e'  # 标题背景（深色，更大气）
    COLOR_TITLE_TEXT = '#FFFFFF'  # 标题文字
    COLOR_SECTION_BG = '#f8f9fa'  # 分组背景
    COLOR_SECTION_TITLE = '#2c3e50'  # 分组标题
    COLOR_BORDER = '#e9ecef'  # 边框
    COLOR_TEXT_PRIMARY = '#2c3e50'  # 主文字
    COLOR_TEXT_SECONDARY = '#6c757d'  # 次要文字
    COLOR_RED = '#e74c3c'  # 红色（涨/买入）
    COLOR_GREEN = '#27ae60'  # 绿色（跌/卖出）
    
    # 尺寸参数
    PADDING = 40  # 整体内边距
    TITLE_HEIGHT = 80  # 标题高度（加大）
    SECTION_PADDING = 20  # 分组内边距
    SECTION_TITLE_HEIGHT = 45  # 分组标题高度
    TABLE_HEADER_HEIGHT = 40  # 表头高度
    ROW_HEIGHT = 35  # 数据行高度
    SECTION_SPACING = 15  # 分组之间的间距
    
    # 列宽
    STOCK_NAME_WIDTH = 140
    BUY_WIDTH = 95
    SELL_WIDTH = 95
    NET_WIDTH = 105
    RATE_WIDTH = 95
    
    # 底部图片参数
    FOOTER_SPACING = 30  # 底部图片与内容的间距
    FOOTER_IMAGE_SIZE = 200  # 底部图片大小（正方形）
    FOOTER_TEXT_SPACING = 15  # 文案与二维码之间的间距
    FOOTER_TEXT_SIZE = 16  # 底部文案字体大小
    
    def __init__(self, font_path: str = None, footer_image_path: str = None, footer_image_paths: List[str] = None):
        """初始化图片生成器
        
        footer_image_path: 单张底部图片（兼容旧用法）
        footer_image_paths: 多张底部图片路径，按顺序排列在底部一行
        """
        self.font_path = font_path or self._get_system_font()
        self.table_width = (self.STOCK_NAME_WIDTH + self.BUY_WIDTH + 
                          self.SELL_WIDTH + self.NET_WIDTH + self.RATE_WIDTH)
        # 支持多张：优先用 footer_image_paths，否则把单张包装成列表
        if footer_image_paths:
            self.footer_image_paths = [p for p in footer_image_paths if p]
        elif footer_image_path:
            self.footer_image_paths = [footer_image_path]
        else:
            self.footer_image_paths = []
        
    def _get_system_font(self) -> str:
        """获取系统中文字体"""
        # macOS - 尝试多个字体路径（按优先级排序）
        fonts_to_try = [
            # macOS 华文黑体（最常见，优先使用）
            '/System/Library/Fonts/STHeiti Medium.ttc',
            '/System/Library/Fonts/STHeiti Light.ttc',
            # macOS 苹方字体
            '/System/Library/Fonts/PingFang.ttc',
            '/System/Library/Fonts/Supplemental/PingFang.ttc',
            # macOS 其他中文字体
            '/System/Library/Fonts/Hiragino Sans GB.ttc',
            '/Library/Fonts/Arial Unicode.ttf',
            '/Library/Fonts/Songti.ttc',
            # Linux
            '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf',
            '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
            '/usr/share/fonts/truetype/arphic/uming.ttc',
            # Windows
            'C:/Windows/Fonts/msyh.ttc',
            'C:/Windows/Fonts/simhei.ttf',
            'C:/Windows/Fonts/simsun.ttc',
        ]
        
        for font_path in fonts_to_try:
            if os.path.exists(font_path):
                print(f"✅ 使用字体: {font_path}")
                return font_path
        
        print("⚠️  警告: 未找到合适的中文字体，可能出现乱码")
        return None
    
    def _get_font(self, size: int, bold: bool = False):
        """获取字体对象"""
        if not IMAGE_SUPPORT:
            return None
            
        if self.font_path and os.path.exists(self.font_path):
            try:
                return ImageFont.truetype(self.font_path, size)
            except Exception as e:
                print(f"⚠️  加载字体失败: {e}")
        
        # 尝试使用系统默认字体
        try:
            return ImageFont.load_default()
        except:
            return None
    
    def _calculate_total_height(self, summary_data: Dict[str, List[Dict]]) -> int:
        """计算总高度"""
        total_height = self.PADDING * 2 + self.TITLE_HEIGHT
        
        for seat_name, trades in summary_data.items():
            # 分组标题 + 表头 + 数据行
            section_height = (self.SECTION_TITLE_HEIGHT + 
                            self.TABLE_HEADER_HEIGHT +
                            len(trades) * self.ROW_HEIGHT + 
                            self.SECTION_PADDING * 2)
            total_height += section_height + self.SECTION_SPACING
        
        # 如果有底部图片，预留空间（包括文案）
        if self.footer_image_paths and any(os.path.exists(p) for p in self.footer_image_paths):
            # 文案高度 + 文案与二维码间距 + 二维码高度 + 底部间距
            total_height += (self.FOOTER_SPACING + self.FOOTER_TEXT_SIZE + 10 + 
                           self.FOOTER_TEXT_SPACING + self.FOOTER_IMAGE_SIZE + self.PADDING)
        
        return total_height
    
    def _draw_text_centered(self, draw, text: str,
                           x: int, y: int, width: int, height: int,
                           font, fill: str):
        """居中绘制文字"""
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        text_x = x + (width - text_width) // 2
        text_y = y + (height - text_height) // 2
        draw.text((text_x, text_y), text, font=font, fill=fill)
    
    def _draw_text_left(self, draw, text: str,
                       x: int, y: int, width: int, height: int,
                       font, fill: str, padding: int = 10):
        """左对齐绘制文字"""
        bbox = draw.textbbox((0, 0), text, font=font)
        text_height = bbox[3] - bbox[1]
        text_x = x + padding
        text_y = y + (height - text_height) // 2
        draw.text((text_x, text_y), text, font=font, fill=fill)
    
    def generate_summary_image(self, trade_date: str, summary_data: Dict[str, List[Dict]], 
                              output_path: str):
        """
        生成龙虎榜汇总图片
        
        Args:
            trade_date: 交易日期
            summary_data: 汇总数据 {游资名称: [交易列表]}
            output_path: 输出路径
        """
        if not IMAGE_SUPPORT:
            print("❌ 无法生成图片：Pillow 未安装")
            return
            
        # 计算图片尺寸
        img_width = self.table_width + self.PADDING * 2
        img_height = self._calculate_total_height(summary_data)
        
        # 创建图片
        img = Image.new('RGB', (img_width, img_height), self.COLOR_BG)
        draw = ImageDraw.Draw(img)
        
        # 字体
        font_title = self._get_font(32, bold=True)
        font_section = self._get_font(18, bold=True)
        font_data = self._get_font(14)
        font_small = self._get_font(12)
        
        current_y = self.PADDING
        
        # 1. 绘制标题
        title_text = f"{trade_date} 龙虎榜"
        title_x = self.PADDING
        draw.rectangle(
            [title_x, current_y, title_x + self.table_width, current_y + self.TITLE_HEIGHT],
            fill=self.COLOR_TITLE_BG
        )
        self._draw_text_centered(
            draw, title_text, title_x, current_y, self.table_width, self.TITLE_HEIGHT,
            font_title, self.COLOR_TITLE_TEXT
        )
        current_y += self.TITLE_HEIGHT + self.SECTION_SPACING
        
        # 2. 绘制每个游资的数据
        for seat_name, trades in summary_data.items():
            section_x = self.PADDING
            section_start_y = current_y
            
            # 分组背景（包含标题、表头、数据）
            section_height = (self.SECTION_TITLE_HEIGHT + 
                            self.TABLE_HEADER_HEIGHT +
                            len(trades) * self.ROW_HEIGHT + 
                            self.SECTION_PADDING * 2)
            draw.rectangle(
                [section_x, section_start_y, 
                 section_x + self.table_width, section_start_y + section_height],
                fill=self.COLOR_SECTION_BG,
                outline=self.COLOR_BORDER,
                width=1
            )
            
            current_y += self.SECTION_PADDING
            
            # 分组标题
            self._draw_text_left(
                draw, f"【{seat_name}】", 
                section_x, current_y, self.table_width, self.SECTION_TITLE_HEIGHT,
                font_section, self.COLOR_SECTION_TITLE, padding=20
            )
            current_y += self.SECTION_TITLE_HEIGHT
            
            # 表头行
            header_y = current_y
            col_x = section_x + 20  # 左边距
            
            # 表头背景（顶到表格两侧边框）
            draw.rectangle(
                [section_x, header_y, 
                 section_x + self.table_width, header_y + self.TABLE_HEADER_HEIGHT],
                fill='#e9ecef',
                outline=self.COLOR_BORDER,
                width=1
            )
            
            # 绘制表头文字
            headers = [
                ('股票名称', self.STOCK_NAME_WIDTH),
                ('买入', self.BUY_WIDTH),
                ('卖出', self.SELL_WIDTH),
                ('净额', self.NET_WIDTH),
                ('涨跌幅', self.RATE_WIDTH)
            ]
            
            for i, (header_text, width) in enumerate(headers):
                if i == 0:
                    # 第一列左对齐
                    self._draw_text_left(
                        draw, header_text,
                        col_x, header_y, width, self.TABLE_HEADER_HEIGHT,
                        font_small, self.COLOR_TEXT_SECONDARY, padding=5
                    )
                else:
                    # 其他列居中对齐
                    self._draw_text_centered(
                        draw, header_text,
                        col_x, header_y, width, self.TABLE_HEADER_HEIGHT,
                        font_small, self.COLOR_TEXT_SECONDARY
                    )
                col_x += width
            
            current_y += self.TABLE_HEADER_HEIGHT
            
            # 绘制数据行
            for trade in trades:
                row_y = current_y
                col_x = section_x + 20  # 左边距，与表头一致
                
                # 股票名称（左对齐）
                self._draw_text_left(
                    draw, trade['股票名称'],
                    col_x, row_y, self.STOCK_NAME_WIDTH, self.ROW_HEIGHT,
                    font_data, self.COLOR_TEXT_PRIMARY, padding=5
                )
                col_x += self.STOCK_NAME_WIDTH
                
                # 买入金额（居中）
                buy_text = trade['买入金额']
                self._draw_text_centered(
                    draw, buy_text,
                    col_x, row_y, self.BUY_WIDTH, self.ROW_HEIGHT,
                    font_small, self.COLOR_TEXT_SECONDARY
                )
                col_x += self.BUY_WIDTH
                
                # 卖出金额（居中）
                sell_text = trade['卖出金额']
                self._draw_text_centered(
                    draw, sell_text,
                    col_x, row_y, self.SELL_WIDTH, self.ROW_HEIGHT,
                    font_small, self.COLOR_TEXT_SECONDARY
                )
                col_x += self.SELL_WIDTH
                
                # 净额（居中，带颜色）
                net_text = trade['买卖金额']
                net_color = (self.COLOR_RED if net_text.startswith('+') 
                           else self.COLOR_GREEN if net_text.startswith('-')
                           else self.COLOR_TEXT_PRIMARY)
                self._draw_text_centered(
                    draw, net_text,
                    col_x, row_y, self.NET_WIDTH, self.ROW_HEIGHT,
                    font_data, net_color
                )
                col_x += self.NET_WIDTH
                
                # 涨跌幅（居中，带颜色）
                rate_text = trade['今日涨跌幅']
                rate_value = float(rate_text.rstrip('%'))
                rate_color = (self.COLOR_RED if rate_value > 0 
                            else self.COLOR_GREEN if rate_value < 0
                            else self.COLOR_TEXT_PRIMARY)
                self._draw_text_centered(
                    draw, rate_text,
                    col_x, row_y, self.RATE_WIDTH, self.ROW_HEIGHT,
                    font_small, rate_color
                )
                
                current_y += self.ROW_HEIGHT
            
            current_y += self.SECTION_PADDING + self.SECTION_SPACING
        
        # 3. 绘制底部图片和文案（如果有）
        valid_footer_paths = [p for p in self.footer_image_paths if p and os.path.exists(p)]
        if valid_footer_paths:
            try:
                # 3.1 绘制文案（在二维码上方）
                footer_text = "扫码关注，精彩不迷路"
                font_footer = self._get_font(self.FOOTER_TEXT_SIZE, bold=False)
                
                if font_footer:
                    # 计算文案位置（居中）
                    text_bbox = draw.textbbox((0, 0), footer_text, font=font_footer)
                    text_width = text_bbox[2] - text_bbox[0]
                    text_x = (img_width - text_width) // 2
                    text_y = current_y + self.FOOTER_SPACING
                    
                    # 绘制文案
                    draw.text(
                        (text_x, text_y),
                        footer_text,
                        font=font_footer,
                        fill=self.COLOR_TEXT_SECONDARY
                    )
                
                # 3.2 多张图片横向排列：根据数量均分宽度，每张等比缩放
                n = len(valid_footer_paths)
                gap = 20  # 图片之间的间距
                available_width = self.table_width - (n - 1) * gap
                single_size = min(self.FOOTER_IMAGE_SIZE, available_width // n)
                footer_y = current_y + self.FOOTER_SPACING + self.FOOTER_TEXT_SIZE + 10 + self.FOOTER_TEXT_SPACING
                total_footer_width = n * single_size + (n - 1) * gap
                start_x = self.PADDING + (self.table_width - total_footer_width) // 2

                for i, path in enumerate(valid_footer_paths):
                    footer_img = Image.open(path)
                    if footer_img.mode == 'RGBA':
                        footer_rgb = Image.new('RGB', footer_img.size, self.COLOR_BG)
                        footer_rgb.paste(footer_img, mask=footer_img.split()[3])
                        footer_img = footer_rgb
                    elif footer_img.mode != 'RGB':
                        footer_img = footer_img.convert('RGB')
                    footer_img.thumbnail(
                        (single_size, single_size),
                        Image.Resampling.LANCZOS
                    )
                    paste_x = start_x + i * (single_size + gap) + (single_size - footer_img.width) // 2
                    paste_y = footer_y + (single_size - footer_img.height) // 2
                    img.paste(footer_img, (paste_x, paste_y))

                print(f"✅ 已追加底部图片和文案: {len(valid_footer_paths)} 张")
            except Exception as e:
                print(f"⚠️  追加底部图片失败: {e}")
                import traceback
                traceback.print_exc()
        
        # 保存图片
        img.save(output_path, 'PNG', quality=95)
        print(f"✅ 汇总图片已生成: {output_path}")


def extract_hot_money_summary(trade_date: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    提取游资龙虎榜汇总数据（合并同一股票的多笔交易）
    """
    print(f"正在提取 {trade_date} 的龙虎榜数据...")
    
    stock_list = get_dragon_tiger_list(trade_date)
    print(f"共找到 {len(stock_list)} 条龙虎榜记录")
    
    # 去重：同一只股票可能因触发多个上榜条件而重复出现
    unique_stocks = {}
    for stock in stock_list:
        code = stock['SECURITY_CODE']
        if code not in unique_stocks:
            unique_stocks[code] = stock
    
    stock_list = list(unique_stocks.values())
    print(f"去重后: {len(stock_list)} 只龙虎榜股票")
    
    # 游资汇总：{游资名称: {股票代码: {合并数据}}}
    hot_money_data = defaultdict(lambda: defaultdict(lambda: {
        'buy_amount': 0,
        'sell_amount': 0,
        'stock_name': '',
        'change_rate': 0
    }))
    
    for idx, stock in enumerate(stock_list, 1):
        security_code = stock['SECURITY_CODE']
        security_name = stock['SECURITY_NAME_ABBR']
        change_rate = stock['CHANGE_RATE']
        
        print(f"[{idx}/{len(stock_list)}] 处理 {security_name} ({security_code})...")
        
        # 获取买入席位
        buy_seats = get_seat_details(trade_date, security_code, 'RPT_BILLBOARD_DAILYDETAILSBUY')
        for seat in buy_seats:
            dept_name = seat.get('OPERATEDEPT_NAME', '')
            seat_name = get_seat_name(dept_name)
            
            if seat_name in SEAT_MAPPING.values():
                buy_amount = seat.get('BUY', 0)
                if buy_amount:
                    # 直接赋值，不累加（同一席位在同一股票上应该只有一条记录）
                    hot_money_data[seat_name][security_code]['buy_amount'] = buy_amount / 10000
                    hot_money_data[seat_name][security_code]['stock_name'] = security_name
                    hot_money_data[seat_name][security_code]['change_rate'] = change_rate
        
        # 获取卖出席位
        sell_seats = get_seat_details(trade_date, security_code, 'RPT_BILLBOARD_DAILYDETAILSSELL')
        for seat in sell_seats:
            dept_name = seat.get('OPERATEDEPT_NAME', '')
            seat_name = get_seat_name(dept_name)
            
            if seat_name in SEAT_MAPPING.values():
                sell_amount = seat.get('SELL', 0)
                if sell_amount:
                    # 直接赋值，不累加（同一席位在同一股票上应该只有一条记录）
                    hot_money_data[seat_name][security_code]['sell_amount'] = sell_amount / 10000
                    hot_money_data[seat_name][security_code]['stock_name'] = security_name
                    hot_money_data[seat_name][security_code]['change_rate'] = change_rate
    
    # 转换为最终格式（保留买入、卖出金额，用于图片生成）
    result = {}
    for seat_name, stocks in hot_money_data.items():
        result[seat_name] = []
        for security_code, data in stocks.items():
            net_amount = data['buy_amount'] - data['sell_amount']
            result[seat_name].append({
                '股票名称': data['stock_name'],
                '股票代码': security_code,
                '买入金额': data['buy_amount'],  # 保留原始买入金额
                '卖出金额': data['sell_amount'],  # 保留原始卖出金额
                '买卖金额': net_amount,  # 保持原始精度，不做四舍五入
                '今日涨跌幅': f"{data['change_rate']:.2f}%"
            })
        
        # 按净买入金额绝对值排序
        result[seat_name].sort(key=lambda x: abs(x['买卖金额']), reverse=True)
    
    return result


def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='游资龙虎榜汇总脚本（简化版）')
    parser.add_argument('-d', '--date', type=str, help='交易日期，格式：YYYY-MM-DD (例如: 2025-12-04)')
    parser.add_argument('--no-image', action='store_true', help='不生成图片')
    parser.add_argument('--image-only', action='store_true', help='仅生成图片，不生成 JSON/YAML')
    parser.add_argument('--footer-image', type=str, action='append', default=[], dest='footer_images',
                        help='底部追加的图片路径，可多次指定（如：--footer-image a.jpg --footer-image b.jpg）')
    args = parser.parse_args()
    
    # 如果提供了日期参数，验证格式；否则使用今天的日期
    if args.date:
        try:
            datetime.strptime(args.date, '%Y-%m-%d')
            trade_date = args.date
        except ValueError:
            print(f"❌ 日期格式错误: {args.date}")
            print("正确格式: YYYY-MM-DD (例如: 2025-12-04)")
            parser.print_help()
            return
    else:
        # 默认使用今天的日期
        trade_date = datetime.now().strftime('%Y-%m-%d')
    
    print(f"提取日期: {trade_date}")
    print(f"席位映射: {len(SEAT_MAPPING)} 条映射关系")
    print("=" * 60)
    
    # 提取数据
    summary = extract_hot_money_summary(trade_date)
    
    # 按游资净交易额排序，拉萨天团放在最后
    def sort_key(item):
        seat_name, trades = item
        # 拉萨天团排在最后，给它一个极小的值
        if seat_name == '拉萨天团':
            return -float('inf')
        # 其他游资按净交易额绝对值降序排列
        return sum(abs(t['买卖金额']) for t in trades)
    
    sorted_summary = dict(sorted(
        summary.items(),
        key=sort_key,
        reverse=True
    ))
    
    # 转换为格式化输出（用于JSON/YAML）
    formatted_summary = {}
    for seat_name, trades in sorted_summary.items():
        formatted_summary[seat_name] = []
        for trade in trades:
            formatted_summary[seat_name].append({
                '股票名称': QuotedString(trade['股票名称']),
                '股票代码': QuotedString(trade['股票代码']),
                '买卖金额': QuotedString(format_amount(trade['买卖金额'])),  # 转换为格式化字符串
                '今日涨跌幅': QuotedString(trade['今日涨跌幅'])
            })
    
    # 输出JSON和YAML（除非只生成图片）
    if not args.image_only:
        # 输出JSON
        json_file = f'leaderboard_{trade_date}.json'
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump({
                '日期': trade_date,
                '游资龙虎榜': formatted_summary
            }, f, ensure_ascii=False, indent=2)
        print(f"\n✅ JSON 文件已保存: {json_file}")
        
        # 输出YAML（支持双引号）
        yaml_file = f'leaderboard_{trade_date}.yaml'
        # 注册自定义表示器，强制字符串使用双引号
        yaml.add_representer(QuotedString, quoted_string_representer)
        with open(yaml_file, 'w', encoding='utf-8') as f:
            yaml.dump({
                '日期': QuotedString(trade_date),
                '游资龙虎榜': formatted_summary
            }, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        print(f"✅ YAML 文件已保存: {yaml_file}")
    
    # 打印简要统计
    print("\n" + "=" * 60)
    print("📊 游资龙虎榜汇总:")
    print(f"活跃游资: {len(sorted_summary)} 个")
    print()
    
    for seat_name, trades in sorted_summary.items():
        total_net = sum(t['买卖金额'] for t in trades)
        print(f"【{seat_name}】")
        for trade in trades:
            # 格式化显示
            amount_value = trade['买卖金额']
            amount_str = format_amount(amount_value)
            # 组合符号和金额（符号紧贴金额）
            if amount_value > 0:
                signed_amount = f"+{amount_str}"
            else:
                signed_amount = amount_str
            # 股票名称按显示宽度对齐（中文占2个宽度，增加到20个宽度）
            padded_name = pad_text(trade['股票名称'], 20)
            # 金额右对齐15个字符（增加宽度以适应更长的数字）
            padded_amount = f"{signed_amount:>15s}"
            # 给涨跌幅添加颜色
            colored_rate = colorize_change_rate(trade['今日涨跌幅'])
            print(f"  {padded_name}{padded_amount}  ({colored_rate})")
        # 净额显示（用分隔线隔开，更美观）
        print(f"  {'─' * 45}")
        total_net_str = format_amount(total_net)
        if total_net > 0:
            net_display = f"+{total_net_str}"
        else:
            net_display = total_net_str
        print(f"  净额: {net_display}")
        print()
    
    # 生成图片（默认生成，除非指定 --no-image）
    if (not args.no_image or args.image_only) and IMAGE_SUPPORT:
        print("\n" + "=" * 60)
        print("🖼️  正在生成汇总图片...")
        
        generator = SummaryImageGenerator(footer_image_paths=args.footer_images or None)
        
        # 准备所有游资的图片数据
        image_summary = {}
        for seat_name, trades in sorted_summary.items():
            image_trades = []
            for trade in trades:
                buy_amount = format_amount(trade['买入金额']) if trade['买入金额'] > 0 else '-'
                sell_amount = format_amount(trade['卖出金额']) if trade['卖出金额'] > 0 else '-'
                net_amount = trade['买卖金额']
                net_amount_str = format_amount(net_amount)
                if net_amount > 0:
                    net_amount_str = f"+{net_amount_str}"
                
                image_trades.append({
                    '股票名称': trade['股票名称'],
                    '买入金额': buy_amount,
                    '卖出金额': sell_amount,
                    '买卖金额': net_amount_str,
                    '今日涨跌幅': trade['今日涨跌幅']
                })
            
            image_summary[seat_name] = image_trades
        
        # 生成汇总图片
        output_path = f'leaderboard_{trade_date}.png'
        try:
            generator.generate_summary_image(
                trade_date=trade_date,
                summary_data=image_summary,
                output_path=output_path
            )
        except Exception as e:
            print(f"❌ 生成图片失败: {e}")
            import traceback
            traceback.print_exc()
    elif (not args.no_image or args.image_only) and not IMAGE_SUPPORT:
        print("\n⚠️  无法生成图片，请运行: uv run leaderboard_summary.py")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()

